#!/bin/bash

# Ensure running as root for deployment
if [ "$EUID" -ne 0 ]; then
  echo "Please run as root (sudo ./deploy.sh)"
  exit 1
fi

echo "Caut un port liber pentru backend-ul aplicatiei..."
BACKEND_PORT=8080
while ss -tuln | grep -q ":$BACKEND_PORT " || netstat -tuln | grep -q ":$BACKEND_PORT "; do
  BACKEND_PORT=$((BACKEND_PORT + 1))
done

echo "Am gasit portul liber: $BACKEND_PORT. Acesta va fi folosit de backend pentru a nu deranja nicio alta aplicatie."

# Modificam Nginx ca sa stie de portul nou
sed -i "s/localhost:[0-9]*/localhost:$BACKEND_PORT/g" /home/micu/unisonTrying/nginx.conf

# Modificam scriptul de backend sa porneasca fix pe acest port
sed -i "s/^PORT=[0-9]*/PORT=$BACKEND_PORT/" /home/micu/unisonTrying/backend/run_backend.sh

echo "Copying Nginx configuration..."
cp /home/micu/unisonTrying/nginx.conf /etc/nginx/sites-available/unison
ln -sf /etc/nginx/sites-available/unison /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

echo "Setting up systemd service..."
cp /home/micu/unisonTrying/unison-backend.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable unison-backend
systemctl restart unison-backend

echo "Reloading Nginx..."
systemctl reload nginx

echo "Setting up SSL with Certbot..."
certbot --nginx -d unison.micutu.com --non-interactive --agree-tos -m alex_mihai984@yahoo.com --redirect

echo "Deployment complete! Application is running at https://unison.micutu.com"
