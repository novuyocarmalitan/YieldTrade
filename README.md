# YIELD-TRADE

An agricultural marketplace that connects smallholder farmers with buyers. Farmers post produce,
buyers post what they need, and a matching engine ranks sellers by how well they fit the order.

Stack: Django REST Framework, React (Vite), SQLite for local development, PostgreSQL for production.

```
YieldTrade/
  backend/    Django REST API, matching engine, order lifecycle
  frontend/   React app for farmers and buyers
```

## How matching works

Every candidate listing gets a score from 0 to 100 against a buyer's request:

| Component | Weight | Meaning |
| --- | --- | --- |
| Price compatibility | 40% | 1.0 when the asking price is at or under the buyer's maximum. It falls in a straight line to 0 once the ask is 25% over that maximum, and anything beyond that is not shown. |
| Volume fulfilment | 60% | The share of the requested quantity the listing can cover, capped at 100%. |

Volume carries more weight because a cheap listing that covers a tenth of an order still leaves the
buyer shopping around, while a slightly dearer one that covers all of it closes the deal. Ties go to the
cheaper ask, then to a seller in the buyer's district. The constants live at the top of
`backend/market/matching.py`.

For each request the API also returns two plans for covering the whole quantity:

- **Best match first**: fewest sellers and the most complete order.
- **Lowest cost**: cheapest sellers first, which may mean more of them.

These are different goals and can disagree. In the demo data, one seller covers a 1,200 kg order for
$456.00 while two cheaper sellers cover it for $392.00, so the app shows both and lets the buyer choose.

Farmers get the mirror image: for each listing, the open buy requests it could fill, ranked the same way.

## Orders

Placing an order reserves stock immediately, so two buyers cannot take the same kilograms. The price is
copied onto the order, so later edits to a listing never change it.

```
pending --accept--> accepted --complete--> completed
   |-- reject (farmer) --> rejected    (stock released)
   '-- cancel (buyer)  --> cancelled   (stock released)
```

Only the farmer can accept, reject or complete. Only the buyer can cancel, and only while the order is
pending. Other users get a 404 for orders that are not theirs, so nothing leaks.

## API

All endpoints except register and login need the header `Authorization: Token <token>`.

| Method and path | Who | Purpose |
| --- | --- | --- |
| `POST /api/auth/register/` | anyone | Create an account (role is `farmer` or `buyer`) |
| `POST /api/auth/login/` | anyone | Returns a token |
| `GET /api/auth/me/` | signed in | Current user |
| `GET /api/crops/` | signed in | Crop catalogue |
| `GET/POST /api/listings/` | read: all, create: farmers | Produce for sale. Filters: `crop`, `status`, `district`, `mine=1` |
| `GET /api/listings/{id}/matches/` | owner farmer | Open buy requests this produce could fill |
| `GET/POST /api/requests/` | read: all, create: buyers | Buy requests. Filters: `crop`, `status`, `mine=1` |
| `GET /api/requests/{id}/matches/` | owner buyer | Ranked sellers plus `plan` and `cheapest_plan` |
| `GET/POST /api/orders/` | signed in | Your orders. POST (buyers) takes `listing`, `quantity_kg`, optional `request` |
| `POST /api/orders/{id}/accept`, `reject`, `cancel`, `complete` | see Orders | Move an order along |

## Run it locally

You need Python 3.10+ and Node 18+. These commands are for Windows `cmd`. On macOS or Linux, use
`source venv/bin/activate` and `cp` instead of `venv\Scripts\activate` and `copy`.

### Backend

```
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```

The API is now at `http://127.0.0.1:8000/api/`. `seed_demo` creates crops and five demo accounts, all with
the password `demo-pass-1234`: `farmer_tendai`, `farmer_rudo`, `farmer_sipho`, `buyer_mill`,
`buyer_grocer`. They are for development only, so never run `seed_demo` against a real deployment.

### Frontend (a second terminal)

```
cd frontend
npm install
copy .env.example .env
npm run dev
```

Open `http://localhost:5173`. Log in as `buyer_mill`, press "Find sellers" on the maize request, and
compare the two plans. Then log in as `farmer_tendai` to accept the resulting orders.

### Tests

```
cd backend
python manage.py test
```

48 tests cover the scoring maths (including the weighting changing rankings), ranking and tie-breaks,
both fulfilment plans, registration and login, permission boundaries, and the order lifecycle: stock
reservation, over-ordering, release on reject or cancel, and orders hidden from outsiders.

## What has and has not been verified

Verified: the 48 backend tests, a run over HTTP against the seeded demo data, and the two main user
journeys (buyer finds sellers and orders a plan, farmer accepts the order) driven through the real React
code against the live backend in a simulated browser.

Not verified: how the screens look in a real browser, the PostgreSQL path, and any deployment. Check
those yourself before relying on them.

## Known limits

- Tokens never expire. Add expiry or move to JWT before a public launch.
- Login throttling uses the default in-memory cache, so it is per process. Use a shared cache in production.
- No payments, delivery tracking, ratings or notifications. An accepted order is a commitment on paper only.
- Money is a single currency shown as `$`.
- Seller and buyer contact details are not exposed through the API yet.

## Deploying

`render.yaml` in the repo root describes the whole deployment for Render: a PostgreSQL database, the
API (gunicorn) and the website (a static site built from `frontend/`). In Render, choose New, then
Blueprint, and pick this repository.

Things to know:

- If a name in `render.yaml` is already taken, change the three names and the two URLs in the env vars.
- On each deploy the API runs migrations and loads the crop catalogue. With `SEED_DEMO=1` it also creates
  the demo accounts. Set `SEED_DEMO` to `0` for anything with real users, because those passwords are public.
- Free web services sleep after 15 minutes idle and take about a minute to wake. Free Render databases
  expire after 30 days, so check Render's current terms.
- For a manual setup the API needs `DJANGO_DEBUG=0`, `DJANGO_SECRET_KEY`, `DATABASE_URL`, and
  `CORS_ALLOWED_ORIGINS` (the website's address). The settings refuse to start without a secret key.

The production-style run (gunicorn, debug off, admin styling, CORS, host checking) was tested locally. The
Render deployment itself and the PostgreSQL connection have not been tested.
