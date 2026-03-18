Maildev Endpoints
GET /email - Get all emails

DELETE /email/all - Delete all emails

GET /email/:id - Get a given email by id

DELETE /email/:id - Delete a given email by id

GET /email/:id/html - Get a given emails html body

GET /email/:id/attachment/:filename - Get a given email's file attachment.

POST /email/:id/relay - If configured, relay a given email to it's real "to" address.

GET /config - Get the application configuration.

GET /healthz - Health check

Pagination
The GET /email endpoint allows for simple skip pagination.

GET /email?skip=10