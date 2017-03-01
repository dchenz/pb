#!/bin/sh -ex

# Upload input to http://pb
#
# usage: pb [-h|--help] [-c|--clip] [-e|--expires <date>] [-l|--label <label>] [<file>...]
#
pb() {
    set +x
    pb_usage() {
        # this needs to be tab-indented.
        >&2 cat <<-EOF
		usage: pb [-h|--help] [-q|--quiet] [-c|--clip] [-e|--expires <date>] [-l|--label <label>] [<file>...]
		EOF
        echo usage
    }

    local pb_base="pb"
    local post_path="/"

    # options
    local clip=0 expires quiet

    local i=1 plain arg opt
    while [ $i -le $# ]; do
        eval "arg=\${$i}"
        eval "opt=\${$((i+1))}"
        case "$arg" in
            -h|--help) pb_usage; exit 0;;
            -q|--quiet) quiet=1;;
            -c|--clip) clip=1;;
            -e|--expires) expires="$opt"; i=$((i+1));;
            -l|--label) post_path="$post_path~$opt"; i=$((i+1));;
            --host) pb_base="$opt"; i=$((i+1));;
            --) i=$((i+1)); break;;
            -) plain="$plain '$arg'";;
            -*) >&2 echo "pb: Unsupported option '$arg'."; pb_usage; exit 3;;
            *) plain="$plain '$arg'";;
        esac
        i=$((i+1))
    done
    while [ $i -le $# ]; do
        eval "arg=\${$i}"
        plain="$plain '$arg'"
        i=$((i+1))
    done
    unset i
    eval "set ${plain:-''}"

    local curlopts redir='>/dev/null'
    if [ -n "$expires" ]; then
        seconds="$(($(date -d "$expires" +%s) - $(date +%s)))"
        if [ "$seconds" -le 0 ]; then
            >&2 echo "pb: The expiration date is set in the past, and no time machine is currently available."
            exit 1
        fi
        curlopts="${curlopts} -F 'sunset=$seconds'"
    fi

    if [ "$clip" -eq 1 ]; then
        if [ -z "$DISPLAY" ]; then
            >&2 echo "pb: Can't copy url to clipboard -- DISPLAY is not defined. If you're using ssh, have you enabled X11 forwarding?"
            exit 1
        fi
        if command -v xclip >/dev/null; then
            >&2 echo "pb: Can't copy url to clipboard -- xclip is not installed."
            exit 1
        fi

        if [ "$quiet" -eq 1 ]; then
            redir='2>/dev/null | xclip -sel clip'
        else
            redir='| xclip -sel clip'
        fi
    elif [ "$quiet" -eq 1 ]; then
        redir='2>/dev/null; echo '
    fi

    curlcmd='curl -sS '"${curlopts}"' -F "c=@${input}" -w "%{redirect_url}" "'"$pb_base$post_path"'?r=1" -o /dev/stderr '"$redir"

    local f
    for f; do
        local input="${f:--}"
        eval "$curlcmd"
    done
}
