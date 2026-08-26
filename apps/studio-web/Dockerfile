FROM nginx:1.27-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY index.html /usr/share/nginx/html/index.html
COPY styles.css /usr/share/nginx/html/styles.css
COPY trend-utils.mjs /usr/share/nginx/html/trend-utils.mjs
COPY app.js /usr/share/nginx/html/app.js

EXPOSE 8080
