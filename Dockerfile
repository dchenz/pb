FROM alpine:3.6

MAINTAINER snaipe@arista.com

ADD http://ftp.gnome.org/pub/GNOME/sources/ttf-bitstream-vera/1.10/ttf-bitstream-vera-1.10.tar.bz2 /root/vera.tar.bz2

RUN apk add --no-cache \
    asciidoctor \
    dumb-init \
    fontconfig \
    git \
    graphicsmagick \
    libmagic \
    libpng-dev \
    nodejs \
    nodejs-npm \
    py3-pillow \
    python3

RUN mkdir -p /usr/share/fonts
RUN tar -C /usr/share/fonts/ -xvjf /root/vera.tar.bz2 $(tar -tjf /root/vera.tar.bz2 | grep '.ttf')
RUN fc-cache -s -f

RUN pip3 install virtualenv
RUN npm install -g grunt-cli

COPY package.json /app/
COPY Gruntfile.js /app/

WORKDIR /app

RUN npm install
# I can't believe I have to do that >:(
RUN cd node_modules/pbs && npm install
RUN grunt
RUN cp -rf node_modules/pbs/dist/css pb/static

COPY requirements.txt.lock /app/
RUN pip3 install -r requirements.txt.lock

COPY config.yaml /root/.config/pb/
COPY run.sh /root/run.sh
ADD . /app

VOLUME /data/db

# clean up
RUN npm uninstall -g grunt-cli && npm prune
RUN apk del git graphicsmagick nodejs nodejs-npm
RUN rm -rf /root/vera.tar.bz2 node_modules

EXPOSE 10002

ENTRYPOINT  [ "dumb-init" ]
CMD         [ "/app/run.py" ]
