# SHEIN WhatsApp Store

This project is a working prototype for a SHEIN WhatsApp ordering system with admin dashboard, supervisor role, customer flow, demo-mode data, and a SQLite database.

## Features

- Flask app with role-based access control
- SQLite database for local development and testing
- Demo users and demo orders
- Customer order creation and tracking
- Payment review flow
- Supervisor and admin dashboards
- Order status updates and notifications
- Basic WhatsApp webhook verification scaffold

## Quick start

1. Create a virtual environment.
2. Install dependencies:
   pip install -r requirements.txt
3. Copy .env.example to .env and adjust values.
4. Run the app:
   python app.py
5. Open http://127.0.0.1:5000/login

## Demo accounts

- admin / DemoAdmin!2026
- supervisor / DemoSupervisor!2026
- customer / DemoCustomer!2026

## Production notes

- Replace demo credentials before deployment.
- Use HTTPS and proper secrets in production.
- Use Meta WhatsApp Cloud API only after verification and proper token configuration.
