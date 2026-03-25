const http = require('http');
const server = http.createServer((req, res) => {
  if (req.url === '/health') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ status: 'ok', service: 'kt-admin', version: '0.1.0' }));
  } else {
    res.writeHead(200, { 'Content-Type': 'text/html' });
    res.end('<html><body><h1>KT Admin Panel</h1><p>Coming soon.</p></body></html>');
  }
});
server.listen(3020, () => console.log('Admin stub running on :3020'));
