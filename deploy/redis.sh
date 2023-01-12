#!/bin/bash
sudo docker rm e_redis
sudo docker run --name='e_redis' --network='host' -d redis
