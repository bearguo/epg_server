FROM frolvlad/alpine-python3:latest

WORKDIR /app/

COPY requirements.txt /app/
COPY epg.py /app/
COPY conf/epg.conf /app/conf/

HEALTHCHECK --interval=5s --timeout=3s CMD curl -fs http://localhost:10010/EPG/channel?secret=VYDcCe1s || exit 1

EXPOSE 10010

CMD ["python", "epg.py"]
RUN apk add --no-cache tzdata curl \
    && ln -sf /usr/share/zoneinfo/Asia/Shanghai /etc/localtime \ 
    && echo "Asia/Shanghai" > /etc/timezone \
    && pip install -r /app/requirements.txt \
    && apk add  
