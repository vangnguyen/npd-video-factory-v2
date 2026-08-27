FROM nginx:1.27-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY index.html /usr/share/nginx/html/index.html
COPY styles.css /usr/share/nginx/html/styles.css
COPY trend-utils.mjs /usr/share/nginx/html/trend-utils.mjs
COPY app.js /usr/share/nginx/html/app.js
COPY studio.html /usr/share/nginx/html/studio.html
COPY studio.css /usr/share/nginx/html/studio.css
COPY studio-utils.mjs /usr/share/nginx/html/studio-utils.mjs
COPY studio.js /usr/share/nginx/html/studio.js

EXPOSE 8080
