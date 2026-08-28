FROM node:22-alpine

WORKDIR /app

COPY package*.json /app/
RUN npm config set fetch-retries 5 \
 && npm config set fetch-retry-mintimeout 20000 \
 && npm config set fetch-retry-maxtimeout 120000 \
 && npm config set strict-ssl false \
 && npm ci --no-audit --no-fund

COPY . /app

EXPOSE 3000
CMD ["npm", "run", "dev", "--", "--hostname", "0.0.0.0", "--port", "3000"]
