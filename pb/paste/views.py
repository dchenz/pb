# -*- coding: utf-8 -*-
"""
    paste.views
    ~~~~~~~~~~~

    paste url routes and views.

    :copyright: Copyright (C) 2015 by the respective authors; see AUTHORS.
    :license: GPLv3, see LICENSE for details.
"""

from uuid import UUID
from mimetypes import guess_type
from io import BytesIO
from urllib.parse import urlencode

from datetime import timedelta, datetime

from flask import Blueprint, request, render_template, current_app, jsonify, make_response
from pygments.formatters import HtmlFormatter, get_all_formatters
from pygments.lexers import get_all_lexers
from pygments.styles import get_all_styles
from pygments.util import ClassNotFound
from pymongo import errors, DESCENDING

from pb.namespace import model as ns_model
from pb.paste import model, handler as _handler
from pb.util import highlight, request_content, request_key_list, request_keys, absolute_url, get_host_name, parse_sunset, asciidoc
from pb.cache import invalidate
from pb.responses import BaseResponse, StatusResponse, PasteResponse, DictResponse, redirect, any_url

paste = Blueprint('paste', __name__)

@paste.app_template_global(name='url')
def _url(endpoint, **kwargs):
    return absolute_url(endpoint, **kwargs)

@paste.route('/')
def index():
    alias_whoami = current_app.config.get('ALIAS_WHOAMI')
    return render_template("index.html", alias_whoami=alias_whoami)

@paste.route('/whoami')
def whoami():
    user = None
    header_name = current_app.config.get('REMOTE_USER_HEADER')
    if header_name:
        user = request.headers.get(header_name)
    return jsonify({"user": user})

def _parse_query_limit():
    try:
        return int(request.args["limit"])
    except Exception:
        return None

def _parse_query_cursor():
    try:
        value = int(request.args["cursor"])
        return datetime.fromtimestamp(value / 1000)
    except Exception:
        return None

def _search_pastes(limit):
    # Only allow filtering on indexed fields.
    valid_search_query_filters = {
        "digest",
        "short",
        "label",
        "tag",
        "mimetype",
    }

    query = {}
    for key in request.args:
        if key not in valid_search_query_filters:
            continue
        values = request.args.getlist(key)
        if key == "tag":
            key = "tags"
        # Multiple values for a query param mean logical OR.
        if len(values) == 1:
            query[key] = values[0]
        else:
            query[key] = {"$in": values}

    cursor = _parse_query_cursor()
    if cursor:
        query["date"] = {"$lt": cursor}

    results = model.get_search_results(**query)
    # Query 1 extra paste so we can tell if there are more pages.
    results = results.limit(limit + 1)
    results = results.sort("date", DESCENDING)

    pastes = [{**paste, "url": any_url(paste)} for paste in results]

    nextCursor = None
    if pastes and len(pastes) > limit:
        pastes.pop()
        nextCursor = int(pastes[-1]["date"].timestamp() * 1000)

    return pastes, nextCursor

@paste.route('/search')
def search():
    defaultSearchLimit = current_app.config.get("DEFAULT_SEARCH_LIMIT", 100)
    maxSearchLimit = current_app.config.get("MAX_SEARCH_LIMIT")

    limit = _parse_query_limit()
    if not limit:
        limit = defaultSearchLimit
    else:
        if limit <= 0:
            return StatusResponse("limit must be greater than zero", 400)
        if maxSearchLimit and limit > maxSearchLimit:
            return StatusResponse(f"limit must be less than {maxSearchLimit}", 400)

    pastes, nextCursor = _search_pastes(limit)

    nextUrl = None
    if nextCursor:
        params = request.args.copy()
        params["cursor"] = str(nextCursor)
        nextUrl = f"{request.path}?{urlencode(params)}"

    mimetype = request.accept_mimetypes.best_match([
        "application/json",
        "text/html",
    ])

    if mimetype == "application/json":
        return jsonify({
            "pastes": pastes,
            "_links": {
                "self": request.full_path,
                "next": nextUrl,
            },
        })

    if mimetype == "text/html":
        response = make_response(render_template("search.html", results=pastes, nextUrl=nextUrl))
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response

    return "", 406

def _auth_namespace(namespace):
    uuid = request.headers.get('X-Namespace-Auth')
    if not uuid:
        return

    try:
        uuid = UUID(uuid)
    except ValueError:
        return

    cur = ns_model.auth(namespace, uuid)
    try:
        return next(cur)
    except StopIteration:
        pass

@paste.route('/<namespace:namespace>', namespace_only=True, methods=['POST'])
@paste.route('/', methods=['POST'])
@paste.route('/<label:label>', methods=['POST'])
def post(label=None, namespace=None):
    stream, filename = request_content()
    if not stream:
        return StatusResponse("no post content", 400)

    cur = model.get_digest(stream)

    args = {}
    if filename:
        args['mimetype'], _ = guess_type(filename)

    for key, value in request_keys('private', 'sunset'):
        try:
            if key == 'sunset':
                args[key] = parse_sunset(value)
            else:
                args[key] = int(value)
        except (ValueError, OverflowError):
            return StatusResponse({
                "invalid request params": {key: value}
            }, 400)

    if label:
        label, _ = label
        if len(label) == 1:
            return StatusResponse("invalid label", 400)
        args['label'] = label
    if namespace:
        host = get_host_name(request)
        if not _auth_namespace(host):
            return StatusResponse("invalid auth", 403)
        label, _ = namespace
        args.update(dict(
            label = label,
            namespace = host
        ))

    tags = request_key_list("tags") or []
    if not (isinstance(tags, list) and all(isinstance(tag, str) for tag in tags)):
        return StatusResponse("invalid tags, expected list[str]", 400)
    args["tags"] = sorted(set(tags))

    if not cur.count():
        try:
            paste = model.insert(stream, **args)
        except errors.DuplicateKeyError:
            return StatusResponse("label already exists.", 409)
        uuid = str(UUID(hex=paste['_id']))
        status = "created"
    else:
        paste = next(cur)
        uuid = None
        status = "already exists"

    return PasteResponse(paste, status, filename, uuid)

def _namespace_kwargs(kwargs):
    host = get_host_name(request)
    if not _auth_namespace(host):
        return StatusResponse("invalid auth", 403)
    label, _ = kwargs['namespace']
    return dict(
        label = label,
        namespace = host,
    )

@paste.route('/<namespace:namespace>', methods=['PUT'], namespace_only=True)
@paste.route('/<uuid:uuid>', methods=['PUT'])
def put(**kwargs):
    if 'namespace' in kwargs:
        kwargs = _namespace_kwargs(kwargs)

    stream, filename = request_content()
    if not stream:
        return StatusResponse("no post content", 400)

    cur = model.get_digest(stream)
    if cur.count():
        return PasteResponse(next(cur), "already exists", filename)

    if filename:
        kwargs['mimetype'], _ = guess_type(filename)

    # FIXME: such query; wow
    invalidate(**kwargs)
    result = model.put(stream, **kwargs)
    if result['n']:
        paste = next(model.get_meta(**kwargs))
        return PasteResponse(paste, "updated")

    return StatusResponse("not found", 404)

@paste.route('/<namespace:namespace>', methods=['DELETE'], namespace_only=True)
@paste.route('/<uuid:uuid>', methods=['DELETE'])
def delete(**kwargs):
    if 'namespace' in kwargs:
        kwargs = _namespace_kwargs(kwargs)

    paste = invalidate(**kwargs)
    result = model.delete(**kwargs)
    if result['n']:
        return PasteResponse(paste, "deleted")
    return StatusResponse("not found", 404)

def _get_paste(cb, sid=None, sha1=None, label=None, namespace=None):
    if sid:
        sid, name, value = sid
        return cb(**{
            'short': sid,
            'private': {
                '$exists': False
            },
            'namespace': {
                '$exists': False
            }
        }), name, value
    if sha1:
        digest, name = sha1[:2]
        return cb(**{
            'digest': digest,
            'namespace': {
                '$exists': False
            }
        }).hint([('digest', 1)]), name, digest
    if label:
        label, name = label
        return cb(**{
            'label': label,
            'namespace': {
                '$exists': False
            }
        }).hint([('label', 1)]), name, label
    if namespace:
        label, name = namespace
        host = get_host_name(request)
        return cb(
            label = label,
            namespace = host
        ), name, label

    return None, None, None

@paste.route('/<namespace:namespace>', methods=['REPORT'], namespace_only=True)
@paste.route('/<sid(length=28):sha1>', methods=['REPORT'])
@paste.route('/<sid(length=4):sid>', methods=['REPORT'])
@paste.route('/<sid(length=8):sid>', methods=['REPORT'])
@paste.route('/<sha1:sha1>', methods=['REPORT'])
@paste.route('/<label:label>', methods=['REPORT'])
def report(sid=None, sha1=None, label=None, namespace=None):
    cur, name, path = _get_paste(model.get_meta, sid, sha1, label, namespace)

    if not cur or not cur.count():
        return StatusResponse("not found", 404)

    paste = next(cur)
    return PasteResponse(paste, "found")

@paste.route('/<namespace:namespace>', namespace_only=True)
@paste.route('/<namespace:namespace>/<string(minlength=0):lexer>', namespace_only=True)
@paste.route('/<namespace:namespace>/<string(minlength=0):lexer>/<formatter>', namespace_only=True)
@paste.route('/<handler:handler>/<namespace:namespace>', namespace_only=True)
@paste.route('/<sid(length=28):sha1>')
@paste.route('/<sid(length=28):sha1>/<string(minlength=0):lexer>')
@paste.route('/<sid(length=28):sha1>/<string(minlength=0):lexer>/<formatter>')
@paste.route('/<handler:handler>/<sid(length=28):sha1>')
@paste.route('/<sid(length=4):sid>')
@paste.route('/<sid(length=4):sid>/<string(minlength=0):lexer>')
@paste.route('/<sid(length=4):sid>/<string(minlength=0):lexer>/<formatter>')
@paste.route('/<sid(length=8):sid>')
@paste.route('/<sid(length=8):sid>/<string(minlength=0):lexer>')
@paste.route('/<sid(length=8):sid>/<string(minlength=0):lexer>/<formatter>')
@paste.route('/<handler:handler>/<sid(length=4):sid>')
@paste.route('/<handler:handler>/<sid(length=8):sid>')
@paste.route('/<sha1:sha1>')
@paste.route('/<sha1:sha1>/<string(minlength=0):lexer>')
@paste.route('/<sha1:sha1>/<string(minlength=0):lexer>/<formatter>')
@paste.route('/<handler:handler>/<sha1:sha1>')
@paste.route('/<label:label>')
@paste.route('/<label:label>/<string(minlength=0):lexer>')
@paste.route('/<label:label>/<string(minlength=0):lexer>/<formatter>')
@paste.route('/<handler:handler>/<label:label>')
def get(sid=None, sha1=None, label=None, namespace=None, lexer=None, handler=None, formatter=None):
    cur, name, path = _get_paste(model.get_content, sid, sha1, label, namespace)

    if not cur or not cur.count():
        return StatusResponse("not found", 404)

    paste = next(cur)
    if paste.get('sunset'):
        request.max_age = parse_sunset(**paste) - datetime.utcnow()
        print('max_age', request.max_age)
        if request.max_age < timedelta():
            uuid = UUID(hex=paste['_id'])
            paste = invalidate(uuid=uuid)
            result = model.delete(uuid=uuid)
            return PasteResponse(paste, "expired", code=410)
        else:
            request.max_age = request.max_age.seconds

    content = model._get(paste.get('content'))

    if paste.get('redirect'):
        content = content.decode('utf-8')
        return redirect(content, content)

    mimetype, _ = guess_type(name)
    if not mimetype:
        mimetype = paste.get('mimetype', 'text/plain')

    if lexer != None:
        content, code, mimetype = highlight(content, lexer, formatter)
        if code != 200:
            return content, code
    if handler != None:
        return _handler.get(handler, content, mimetype, path=path)

    return BaseResponse(content, mimetype=mimetype)

@paste.route('/<handler:handler>', methods=['POST'])
def preview(handler):
    stream, filename = request_content()

    if not stream:
        return ''

    mimetype = None
    if filename:
        mimetype, _ = guess_type(filename)

    return _handler.get(handler, stream.read(), mimetype, partial=True)

@paste.route('/u', methods=['POST'])
def url():
    stream, _ = request_content()
    if not stream:
        return StatusResponse("no post content", 400)

    stream = BytesIO(stream.read().decode('utf-8').split()[0].encode('utf-8'))

    cur = model.get_digest(stream)
    if not cur.count():
        url = model.insert(stream, redirect=1)
        status = "created"
    else:
        url = next(cur)
        status = "already exists"

    return PasteResponse(url, status)

@paste.route('/s')
def stats():
    cur = model.get_meta()
    return DictResponse(dict(pastes=cur.count()))

@paste.route('/static/<style>.css')
def highlight_css(style="default"):
    try:
        css = HtmlFormatter(style=style).get_style_defs('body')
    except ClassNotFound:
        return StatusResponse("not found", 404)

    return BaseResponse(css, mimetype='text/css')

@paste.route('/lf')
def list_formatters():
    formatters = [i.aliases for i in get_all_formatters()]
    return DictResponse(formatters)

@paste.route('/l')
def list_lexers():
    lexers = [i for _, i, _, _ in get_all_lexers()]
    return DictResponse(lexers)

@paste.route('/ls')
def list_styles():
    return DictResponse(list(get_all_styles()))

@paste.route('/man')
def manpage_html():
    return asciidoc(render_template("pb.txt"), backend='html5')

@paste.route('/man.1')
def manpage_docbook():
    return BaseResponse(asciidoc(render_template("pb.txt")), mimetype="text/plain")

@paste.route('/sh')
def shell_func():
    alias_whoami = current_app.config.get('ALIAS_WHOAMI')
    return BaseResponse(render_template("pb.sh", alias_whoami=alias_whoami), mimetype="text/plain")
