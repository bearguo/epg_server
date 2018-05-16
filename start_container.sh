#!/bin/bash
set -e

EPG_DOCKER_IMAGE=registry.cn-hangzhou.aliyuncs.com/tongshi/epg:latest
# pull the latest epg image from registry
docker pull $EPG_DOCKER_IMAGE
# stop and remove existing epg container
docker rm -f epg && exit 0
# run the latest epg container
docker run -p 10010:10010 \
-v /home/share/epg_server/conf:/app/conf \
-d \
--restart=always \
--name epg \
$EPG_DOCKER_IMAGE
