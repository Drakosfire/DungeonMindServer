> **Historical import from DungeonOverMind — 2026-09-24.** This document records an older backend/deployment implementation state. It is not current DungeonMindServer architecture or sequencing authority. Re-anchor against current code/configuration before applying it.

# Nginx Configuration Guide for React Applications

## Basic Structure
A typical Nginx configuration for a React application with a backend API consists of:
- SSL configuration
- Static file serving
- React route handling
- Backend API proxying

## Key Components

### SSL Configuration 

nginx
server {
listen 443 ssl;
server_name example.com www.example.com;
ssl_certificate /path/to/fullchain.pem;
ssl_certificate_key /path/to/privkey.pem;
}

### React Route Handling

```nginx
location / {
    root /path/to/react/build;
    index index.html;
    
    # Critical line for React routing
    try_files $uri $uri/ /index.html @backend;
}
```

The `try_files` directive attempts to serve in this order:
1. Exact URI match (`$uri`)
2. URI as a directory (`$uri/`)
3. React's index.html
4. Backend fallback (`@backend`)

### Backend Proxy

```nginx
location @backend {
    proxy_pass http://localhost:your_port;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    
    # Cookie handling for cross-origin requests
    proxy_cookie_path / "/; Secure; HttpOnly; SameSite=None";
    proxy_set_header Cookie $http_cookie;
    proxy_set_header Set-Cookie $upstream_http_set_cookie;
}
```

## Common Issues and Solutions

### Direct URL Access Not Working
If direct URL access to React routes (like `/somepage`) returns 404:
- Ensure `try_files` includes `/index.html`
- Check that the root path points to your React build directory

### Backend Connection Issues (502 Bad Gateway)
If you get a 502 error:
1. Verify backend server is running
2. Check nginx error logs: `sudo tail -f /var/log/nginx/error.log`
3. Test backend directly: `curl http://localhost:your_port`

### SSL Certificate Issues
For development:
- Use `-k` flag with curl to ignore SSL verification
- Use `mkcert` for local SSL certificates

```bash
mkcert -install
mkcert domain.local localhost 127.0.0.1
```

For production:
- Use Let's Encrypt certificates

```bash
sudo certbot --nginx -d example.com -d www.example.com
```

## Useful Commands

### Configuration Testing

```bash
# Test nginx configuration
sudo nginx -t

# Reload nginx configuration
sudo systemctl reload nginx

# View logs
sudo tail -f /var/log/nginx/error.log
sudo tail -f /var/log/nginx/access.log
```

### File Permissions

```bash
# Set proper ownership
sudo chown -R www-data:www-data /var/www/your_app

# Set proper permissions
sudo chmod -R 755 /var/www/your_app
```

## Best Practices
1. Always test configuration before reloading
2. Use named locations (`@backend`) for cleaner configuration
3. Include proper headers for security and CORS
4. Set appropriate buffer sizes for file uploads
5. Enable HTTPS redirect for HTTP traffic
6. Keep logs for debugging
7. Use environment-specific configurations for development and production

Remember to adjust paths, port numbers, and domain names according to your specific setup.
```

You can save this file in your project's documentation directory or wherever you keep your technical documentation. Would you like me to suggest a specific location for this file?
