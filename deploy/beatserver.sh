#!/bin/bash
sudo docker rm e_beatserver
sudo docker run --name='e_beatserver' --network='host' e_app ./manage.py beatserver
