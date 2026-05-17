Seed demo users and test data for local development.

**Create demo users (all roles):**
```bash
make seed
```

Or manually:
```bash
# Admin
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@claimsiq.com","password":"Admin1234!","full_name":"System Administrator","role":"ADMIN"}'

# Claims Processor
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"processor@claimsiq.com","password":"Processor1!","full_name":"Sarah Mitchell","role":"CLAIM_PROCESSOR"}'

# Provider (NPI: 1234567890)
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"provider@citymed.com","password":"Provider1!","full_name":"Dr. James Park","role":"PROVIDER","provider_npi":"1234567890","provider_name":"City Medical Center"}'

# Patient
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"patient@example.com","password":"Patient1!","full_name":"Alex Johnson","role":"PATIENT"}'
```

**Register a member + policy via admin token:**
```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -d "username=admin@claimsiq.com&password=Admin1234!" | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

curl -X POST http://localhost:8000/api/v1/members \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"member_id":"MBR-001","name":"Test Patient","date_of_birth":"1985-06-15","email":"patient@example.com"}'
```
