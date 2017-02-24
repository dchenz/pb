FROM alpine:edge

MAINTAINER snaipe@arista.com

RUN echo http://dl-4.alpinelinux.org/alpine/edge/testing >> /etc/apk/repositories
RUN apk add --no-cache mongodb python3 git nodejs graphicsmagick

RUN rm /usr/bin/mongosniff /usr/bin/mongoperf

RUN pip3 install virtualenv
RUN npm install -g grunt-cli

COPY package.json /app/
COPY Gruntfile.js /app/

RUN cd app && npm install
# I can't believe I have to do that >:(
RUN cd app/node_modules/pbs && npm install
RUN cd app && grunt

COPY requirements.txt /app/
RUN pip3 install -r /app/requirements.txt

COPY config.yaml /root/.config/pb/
COPY run.sh /root/run.sh
ADD . /app

VOLUME /data/db

RUN mongod & /app/runonce.py

RUN apk del git graphicsmagick nodejs

EXPOSE 10002

ENTRYPOINT  [ "/root/run.sh" ]
CMD         [ "pb" ]
