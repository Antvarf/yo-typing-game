ssh app_manager@yo-typing.ru <<EOF
cd /var/www/E
git pull
sudo docker-compose build migrate
sudo systemctl restart E_app
EOF
