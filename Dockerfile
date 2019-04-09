FROM frolvlad/alpine-python3:latest

WORKDIR /app/

COPY requirements.txt /app/

RUN pip install -r /app/requirements.txt &&\
    apk add --no-cache curl tzdata && \
    ln -sf /usr/share/zoneinfo/Asia/Shanghai /etc/localtime && \ 
    echo "Asia/Shanghai" > /etc/timezone && \
    rm -rf /var/cache 

HEALTHCHECK --interval=30s --timeout=3s --start-period=600s CMD curl -fs http://localhost:10010/EPG/channel?secret=VYDcCe1s || exit 1
EXPOSE 10010
COPY epg.py /app
CMD ["python", "epg.py"]


