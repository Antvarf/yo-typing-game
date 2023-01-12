cd /var/www/E
git pull
sudo docker build -t e_app .
sudo docker run e_app bash -c "./manage.py makemigrations --noinput && ./manage.py migrate && ./manage.py test"
sudo docker-compose build migrate
sudo systemctl restart E_app
