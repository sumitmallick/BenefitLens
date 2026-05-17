Start the full ClaimsIQ development environment.

```bash
make dev
```

This runs `docker compose up -d --build` which starts:
- **PostgreSQL 16** on port 5432
- **Redis 7** on port 6379
- **FastAPI backend** on port 8000 (hot-reload via uvicorn --reload)
- **Next.js frontend** on port 3000

After startup, apply migrations and seed demo users:
```bash
make migrate
make seed
```

Then open http://localhost:3000 and log in with:
- **Admin:** admin@claimsiq.com / Admin1234!
- **Processor:** processor@claimsiq.com / Processor1!
- **Provider:** provider@citymed.com / Provider1!
- **Patient:** patient@example.com / Patient1!

Backend API docs: http://localhost:8000/docs

To follow logs: `make logs`
To stop everything: `make down`
