FROM nginx:alpine
RUN rm -rf /usr/share/nginx/html/*
COPY web_application /usr/share/nginx/html/

RUN sed -i 's/listen\s*80;/listen 8470;/; s/index  index.html index.htm;/index HW1-PragnayaPriyadarshini.html index.html index.htm;/' /etc/nginx/conf.d/default.conf

EXPOSE 8470
CMD ["nginx", "-g", "daemon off;"]
