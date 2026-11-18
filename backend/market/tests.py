from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient

from . import matching
from .models import BuyRequest, Crop, Listing, Order, Profile

User = get_user_model()
D = Decimal


# ------------------------------------------------------------------ matching engine (pure maths)

class ScoreMathTests(SimpleTestCase):
    def test_weights_sum_to_one(self):
        self.assertAlmostEqual(matching.PRICE_WEIGHT + matching.VOLUME_WEIGHT, 1.0)
        self.assertEqual((matching.PRICE_WEIGHT, matching.VOLUME_WEIGHT), (0.40, 0.60))

    def test_price_score_at_or_under_budget_is_perfect(self):
        self.assertEqual(matching.price_score(D("0.30"), D("0.35")), 1.0)
        self.assertEqual(matching.price_score(D("0.35"), D("0.35")), 1.0)

    def test_price_score_decays_linearly_over_the_tolerance_band(self):
        self.assertAlmostEqual(matching.price_score(D("1.125"), D("1.00")), 0.5)
        self.assertAlmostEqual(matching.price_score(D("1.25"), D("1.00")), 0.0)
        self.assertEqual(matching.price_score(D("2.00"), D("1.00")), 0.0)

    def test_volume_score_is_capped_at_full_coverage(self):
        self.assertAlmostEqual(matching.volume_score(500, 1000), 0.5)
        self.assertEqual(matching.volume_score(5000, 1000), 1.0)

    def test_degenerate_inputs_score_zero_instead_of_crashing(self):
        self.assertEqual(matching.volume_score(100, 0), 0.0)
        self.assertEqual(matching.volume_score(0, 100), 0.0)
        self.assertEqual(matching.price_score(1, 0), 0.0)

    def test_total_blends_forty_sixty(self):
        s = matching.score(ask=D("0.30"), max_price=D("0.35"), available=500, needed=1000)
        self.assertAlmostEqual(s.total, 100 * (0.4 * 1.0 + 0.6 * 0.5))  # 70
        self.assertEqual(s.to_dict(), {"score": 70.0, "price_score": 100.0, "volume_score": 50.0})

    def test_volume_outweighs_price(self):
        cheap_but_small = matching.score(D("0.20"), D("0.40"), 200, 1000)    # price 1.0, volume 0.2
        pricier_but_full = matching.score(D("0.42"), D("0.40"), 1000, 1000)  # price 0.8, volume 1.0
        self.assertGreater(pricier_but_full.total, cheap_but_small.total)


# ------------------------------------------------------------------ shared fixtures

class Base(TestCase):
    def setUp(self):
        cache.clear()  # auth throttling lives in the cache
        self.maize = Crop.objects.create(name="Maize")
        self.beans = Crop.objects.create(name="Beans")
        self.farmer = self.make_user("farmer1", Profile.FARMER, "Gwanda")
        self.farmer2 = self.make_user("farmer2", Profile.FARMER, "Umguza")
        self.buyer = self.make_user("buyer1", Profile.BUYER, "Bulawayo")
        self.buyer2 = self.make_user("buyer2", Profile.BUYER, "Bulawayo")

    @staticmethod
    def make_user(name, role, district=""):
        u = User.objects.create_user(username=name, password="s3cret-pass-99")
        Profile.objects.create(user=u, role=role, district=district)
        return u

    def client_for(self, user):
        from rest_framework.authtoken.models import Token
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION=f"Token {Token.objects.get_or_create(user=user)[0].key}")
        return c

    def listing(self, farmer=None, crop=None, qty=500, price="0.30", district="Gwanda", **kw):
        return Listing.objects.create(farmer=farmer or self.farmer, crop=crop or self.maize, quantity_kg=D(str(qty)),
                                      price_per_kg=D(price), district=district, available_from=date.today(), **kw)

    def request_(self, buyer=None, crop=None, qty=1000, price="0.35", district="Bulawayo"):
        return BuyRequest.objects.create(buyer=buyer or self.buyer, crop=crop or self.maize, quantity_kg=D(str(qty)),
                                         max_price_per_kg=D(price), district=district,
                                         needed_by=date.today() + timedelta(days=7))


# ------------------------------------------------------------------ ranking and plan

class RankingTests(Base):
    def test_excludes_other_crops_closed_listings_and_priced_out_listings(self):
        req = self.request_(price="0.35")
        ok = self.listing(price="0.30")
        self.listing(crop=self.beans)
        self.listing(price="0.30", status=Listing.CLOSED)
        self.listing(price="0.50")  # 43% over budget: outside the 25% tolerance
        ranked = matching.rank_listings(req, Listing.objects.all())
        self.assertEqual([l.pk for l, _ in ranked], [ok.pk])

    def test_ranks_by_blended_score(self):
        req = self.request_(qty=1000, price="0.40")
        small_cheap = self.listing(qty=200, price="0.20")
        big_slightly_dear = self.listing(qty=1000, price="0.42")
        ranked = matching.rank_listings(req, Listing.objects.all())
        self.assertEqual([l.pk for l, _ in ranked], [big_slightly_dear.pk, small_cheap.pk])

    def test_ties_go_to_the_cheaper_ask_then_the_local_listing(self):
        req = self.request_(qty=100, price="0.50", district="Gwanda")
        dear = self.listing(qty=500, price="0.40", district="Gwanda")
        cheap_far = self.listing(qty=500, price="0.30", district="Umguza", farmer=self.farmer2)
        cheap_local = self.listing(qty=500, price="0.30", district="Gwanda")
        ranked = [l.pk for l, _ in matching.rank_listings(req, Listing.objects.all())]
        self.assertEqual(ranked, [cheap_local.pk, cheap_far.pk, dear.pk])

    def test_rank_requests_is_the_mirror_for_farmers(self):
        lst = self.listing(qty=600, price="0.30")
        full = self.request_(qty=500, price="0.35")
        partial = self.request_(qty=2000, price="0.35", buyer=self.buyer2)
        self.request_(price="0.10")  # cannot afford it
        ranked = [r.pk for r, _ in matching.rank_requests(lst, BuyRequest.objects.all())]
        self.assertEqual(ranked, [full.pk, partial.pk])

    def test_closed_listing_matches_nothing(self):
        lst = self.listing(status=Listing.CLOSED)
        self.request_()
        self.assertEqual(matching.rank_requests(lst, BuyRequest.objects.all()), [])

    def test_fulfilment_plan_fills_from_the_best_match_down(self):
        req = self.request_(qty=1000, price="0.40")
        a = self.listing(qty=600, price="0.30")
        b = self.listing(qty=300, price="0.35", farmer=self.farmer2)
        plan = matching.fulfilment_plan(req, matching.rank_listings(req, Listing.objects.all()))
        self.assertEqual(plan["covered_kg"], "900.00")
        self.assertEqual(plan["shortfall_kg"], "100.00")
        self.assertEqual(plan["covered_pct"], 90.0)
        self.assertEqual(plan["total_cost"], "285.00")  # 600*0.30 + 300*0.35
        self.assertEqual(plan["avg_price_per_kg"], "0.32")
        self.assertEqual([l["listing"] for l in plan["lines"]], [a.pk, b.pk])

    def test_cost_strategy_can_beat_the_score_strategy_on_price(self):
        # One seller covers everything but sits above budget; two cheaper sellers together cost less.
        req = self.request_(qty=1200, price="0.36")
        self.listing(qty=1500, price="0.38", farmer=self.farmer2)
        self.listing(qty=800, price="0.34")
        self.listing(qty=400, price="0.30", farmer=self.buyer2)  # seller identity is irrelevant to the maths
        ranked = matching.rank_listings(req, Listing.objects.all())
        by_score = matching.fulfilment_plan(req, ranked, by="score")
        by_cost = matching.fulfilment_plan(req, ranked, by="cost")
        self.assertEqual((by_score["sellers"], by_score["total_cost"]), (1, "456.00"))
        self.assertEqual((by_cost["sellers"], by_cost["total_cost"]), (2, "392.00"))
        self.assertEqual(by_cost["covered_pct"], 100.0)

    def test_plan_stops_once_the_request_is_covered(self):
        req = self.request_(qty=400, price="0.40")
        self.listing(qty=500, price="0.30")
        self.listing(qty=500, price="0.31", farmer=self.farmer2)
        plan = matching.fulfilment_plan(req, matching.rank_listings(req, Listing.objects.all()))
        self.assertEqual(len(plan["lines"]), 1)
        self.assertEqual(plan["shortfall_kg"], "0.00")

    def test_plan_with_no_matches(self):
        plan = matching.fulfilment_plan(self.request_(), [])
        self.assertEqual((plan["covered_kg"], plan["covered_pct"], plan["avg_price_per_kg"]), ("0.00", 0.0, None))


# ------------------------------------------------------------------ auth

class AuthTests(Base):
    def test_register_login_me(self):
        c = APIClient()
        r = c.post("/api/auth/register/", {"username": "newfarmer", "password": "a-good-pass-77", "role": "farmer", "district": "Gwanda"}, format="json")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()["user"]["role"], "farmer")
        r = c.post("/api/auth/login/", {"username": "newfarmer", "password": "a-good-pass-77"}, format="json")
        self.assertEqual(r.status_code, 200)
        c.credentials(HTTP_AUTHORIZATION=f"Token {r.json()['token']}")
        self.assertEqual(c.get("/api/auth/me/").json()["username"], "newfarmer")

    def test_register_rejects_weak_password_duplicate_name_and_bad_role(self):
        c = APIClient()
        self.assertEqual(c.post("/api/auth/register/", {"username": "x1", "password": "12345678", "role": "farmer"}, format="json").status_code, 400)
        self.assertEqual(c.post("/api/auth/register/", {"username": "FARMER1", "password": "a-good-pass-77", "role": "farmer"}, format="json").status_code, 400)
        self.assertEqual(c.post("/api/auth/register/", {"username": "x2", "password": "a-good-pass-77", "role": "admin"}, format="json").status_code, 400)

    def test_login_failure_does_not_reveal_which_part_was_wrong(self):
        c = APIClient()
        a = c.post("/api/auth/login/", {"username": "farmer1", "password": "wrong"}, format="json")
        b = c.post("/api/auth/login/", {"username": "nobody", "password": "wrong"}, format="json")
        self.assertEqual((a.status_code, a.json()), (b.status_code, b.json()))

    def test_endpoints_require_a_token(self):
        for url in ("/api/listings/", "/api/requests/", "/api/orders/", "/api/auth/me/"):
            self.assertEqual(APIClient().get(url).status_code, 401, url)

    def test_login_is_throttled(self):
        c = APIClient()
        codes = [c.post("/api/auth/login/", {"username": "a", "password": "b"}, format="json").status_code for _ in range(32)]
        self.assertEqual(codes[-1], 429)


# ------------------------------------------------------------------ listings and requests

class ListingApiTests(Base):
    payload = lambda self: {"crop": self.maize.pk, "quantity_kg": "500", "price_per_kg": "0.30", "district": "Gwanda",
                            "available_from": str(date.today())}

    def test_farmer_creates_listing_and_is_recorded_as_owner(self):
        r = self.client_for(self.farmer).post("/api/listings/", self.payload(), format="json")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(Listing.objects.get(pk=r.json()["id"]).farmer, self.farmer)

    def test_buyer_cannot_create_a_listing(self):
        self.assertEqual(self.client_for(self.buyer).post("/api/listings/", self.payload(), format="json").status_code, 403)

    def test_cannot_spoof_the_owner_field(self):
        body = {**self.payload(), "farmer": self.farmer2.pk}
        r = self.client_for(self.farmer).post("/api/listings/", body, format="json")
        self.assertEqual(Listing.objects.get(pk=r.json()["id"]).farmer, self.farmer)

    def test_rejects_zero_quantity_and_non_positive_price(self):
        c = self.client_for(self.farmer)
        self.assertEqual(c.post("/api/listings/", {**self.payload(), "quantity_kg": "0"}, format="json").status_code, 400)
        self.assertEqual(c.post("/api/listings/", {**self.payload(), "price_per_kg": "-1"}, format="json").status_code, 400)

    def test_only_the_owner_can_edit_or_delete(self):
        lst = self.listing()
        other = self.client_for(self.farmer2)
        self.assertEqual(other.patch(f"/api/listings/{lst.pk}/", {"price_per_kg": "9"}, format="json").status_code, 403)
        self.assertEqual(other.delete(f"/api/listings/{lst.pk}/").status_code, 403)
        mine = self.client_for(self.farmer)
        self.assertEqual(mine.patch(f"/api/listings/{lst.pk}/", {"price_per_kg": "0.31"}, format="json").status_code, 200)

    def test_deleting_a_listing_with_orders_closes_it_instead(self):
        lst = self.listing()
        Order.objects.create(listing=lst, buyer=self.buyer, quantity_kg=D("10"), price_per_kg=lst.price_per_kg)
        self.assertEqual(self.client_for(self.farmer).delete(f"/api/listings/{lst.pk}/").status_code, 204)
        lst.refresh_from_db()
        self.assertEqual(lst.status, Listing.CLOSED)

    def test_filters(self):
        self.listing(crop=self.maize)
        self.listing(crop=self.beans, farmer=self.farmer2)
        c = self.client_for(self.farmer)
        self.assertEqual(c.get(f"/api/listings/?crop={self.beans.pk}").json()["count"], 1)
        self.assertEqual(c.get("/api/listings/?mine=1").json()["count"], 1)

    def test_listing_matches_endpoint_is_owner_only_and_ranked(self):
        lst = self.listing(qty=600, price="0.30")
        good = self.request_(qty=500, price="0.35")
        self.request_(price="0.10")
        r = self.client_for(self.farmer).get(f"/api/listings/{lst.pk}/matches/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual([m["request"]["id"] for m in r.json()["matches"]], [good.pk])
        self.assertEqual(self.client_for(self.farmer2).get(f"/api/listings/{lst.pk}/matches/").status_code, 403)
        self.assertEqual(self.client_for(self.buyer).get(f"/api/listings/{lst.pk}/matches/").status_code, 403)

    def test_request_matches_endpoint_returns_ranking_weights_and_plan(self):
        req = self.request_(qty=1000, price="0.40")
        self.listing(qty=600, price="0.30")
        r = self.client_for(self.buyer).get(f"/api/requests/{req.pk}/matches/")
        body = r.json()
        self.assertEqual(body["weights"], {"price": 0.4, "volume": 0.6})
        self.assertEqual(len(body["matches"]), 1)
        self.assertEqual(body["matches"][0]["score"], 76.0)  # 0.4*1 + 0.6*0.6
        self.assertEqual(body["plan"]["covered_pct"], 60.0)
        self.assertEqual(body["cheapest_plan"]["strategy"], "cost")
        self.assertEqual(self.client_for(self.buyer2).get(f"/api/requests/{req.pk}/matches/").status_code, 403)

    def test_farmer_cannot_create_a_buy_request(self):
        body = {"crop": self.maize.pk, "quantity_kg": "100", "max_price_per_kg": "0.4", "needed_by": str(date.today())}
        self.assertEqual(self.client_for(self.farmer).post("/api/requests/", body, format="json").status_code, 403)
        self.assertEqual(self.client_for(self.buyer).post("/api/requests/", body, format="json").status_code, 201)


# ------------------------------------------------------------------ orders

class OrderTests(Base):
    def place(self, user, listing, qty, request=None):
        body = {"listing": listing.pk, "quantity_kg": str(qty)}
        if request:
            body["request"] = request.pk
        return self.client_for(user).post("/api/orders/", body, format="json")

    def test_placing_an_order_reserves_stock_and_snapshots_the_price(self):
        lst = self.listing(qty=500, price="0.30")
        r = self.place(self.buyer, lst, 200)
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()["total"], "60.00")
        lst.refresh_from_db()
        self.assertEqual(lst.quantity_kg, D("300.00"))
        lst.price_per_kg = D("0.99")
        lst.save()
        self.assertEqual(Order.objects.get().price_per_kg, D("0.30"))

    def test_cannot_order_more_than_is_available(self):
        lst = self.listing(qty=100)
        r = self.place(self.buyer, lst, 101)
        self.assertEqual(r.status_code, 400)
        lst.refresh_from_db()
        self.assertEqual(lst.quantity_kg, D("100.00"))
        self.assertEqual(Order.objects.count(), 0)

    def test_second_buyer_cannot_take_what_the_first_reserved(self):
        lst = self.listing(qty=100)
        self.assertEqual(self.place(self.buyer, lst, 80).status_code, 201)
        self.assertEqual(self.place(self.buyer2, lst, 30).status_code, 400)
        self.assertEqual(self.place(self.buyer2, lst, 20).status_code, 201)

    def test_selling_out_closes_the_listing(self):
        lst = self.listing(qty=100)
        self.place(self.buyer, lst, 100)
        lst.refresh_from_db()
        self.assertEqual((lst.status, lst.quantity_kg), (Listing.CLOSED, D("0.00")))
        self.assertEqual(self.place(self.buyer2, lst, 1).status_code, 400)

    def test_farmers_cannot_place_orders(self):
        self.assertEqual(self.place(self.farmer2, self.listing(), 10).status_code, 403)

    def test_reject_releases_stock_and_reopens_a_sold_out_listing(self):
        lst = self.listing(qty=100)
        oid = self.place(self.buyer, lst, 100).json()["id"]
        r = self.client_for(self.farmer).post(f"/api/orders/{oid}/reject/")
        self.assertEqual((r.status_code, r.json()["status"]), (200, "rejected"))
        lst.refresh_from_db()
        self.assertEqual((lst.status, lst.quantity_kg), (Listing.OPEN, D("100.00")))

    def test_buyer_cancel_releases_stock(self):
        lst = self.listing(qty=100)
        oid = self.place(self.buyer, lst, 40).json()["id"]
        self.assertEqual(self.client_for(self.buyer).post(f"/api/orders/{oid}/cancel/").json()["status"], "cancelled")
        lst.refresh_from_db()
        self.assertEqual(lst.quantity_kg, D("100.00"))

    def test_a_listing_the_farmer_closed_by_hand_stays_closed_after_a_cancel(self):
        lst = self.listing(qty=100)
        oid = self.place(self.buyer, lst, 40).json()["id"]
        lst.refresh_from_db()
        lst.status = Listing.CLOSED
        lst.save()
        self.client_for(self.buyer).post(f"/api/orders/{oid}/cancel/")
        lst.refresh_from_db()
        self.assertEqual(lst.status, Listing.CLOSED)

    def test_happy_path_accept_then_complete_keeps_stock_reserved(self):
        lst = self.listing(qty=100)
        oid = self.place(self.buyer, lst, 60).json()["id"]
        f = self.client_for(self.farmer)
        self.assertEqual(f.post(f"/api/orders/{oid}/accept/").json()["status"], "accepted")
        self.assertEqual(f.post(f"/api/orders/{oid}/complete/").json()["status"], "completed")
        lst.refresh_from_db()
        self.assertEqual(lst.quantity_kg, D("40.00"))

    def test_role_and_state_rules(self):
        lst = self.listing(qty=100)
        oid = self.place(self.buyer, lst, 10).json()["id"]
        b, f = self.client_for(self.buyer), self.client_for(self.farmer)
        self.assertEqual(b.post(f"/api/orders/{oid}/accept/").status_code, 403)    # buyers cannot accept
        self.assertEqual(f.post(f"/api/orders/{oid}/cancel/").status_code, 403)    # farmers cannot cancel
        self.assertEqual(f.post(f"/api/orders/{oid}/complete/").status_code, 400)  # must be accepted first
        f.post(f"/api/orders/{oid}/accept/")
        self.assertEqual(b.post(f"/api/orders/{oid}/cancel/").status_code, 400)    # too late to cancel
        self.assertEqual(f.post(f"/api/orders/{oid}/reject/").status_code, 400)

    def test_outsiders_cannot_see_or_touch_an_order(self):
        oid = self.place(self.buyer, self.listing(qty=100), 10).json()["id"]
        for user in (self.buyer2, self.farmer2):
            c = self.client_for(user)
            self.assertEqual(c.get(f"/api/orders/{oid}/").status_code, 404)
            self.assertEqual(c.post(f"/api/orders/{oid}/accept/").status_code, 404)
            self.assertEqual(c.get("/api/orders/").json()["count"], 0)

    def test_each_side_sees_its_own_orders(self):
        self.place(self.buyer, self.listing(qty=100), 10)
        self.assertEqual(self.client_for(self.buyer).get("/api/orders/").json()["count"], 1)
        self.assertEqual(self.client_for(self.farmer).get("/api/orders/").json()["count"], 1)

    def test_request_becomes_fulfilled_and_reopens_when_an_order_falls_away(self):
        req = self.request_(qty=100)
        lst = self.listing(qty=500)
        oid = self.place(self.buyer, lst, 100, request=req).json()["id"]
        req.refresh_from_db()
        self.assertEqual(req.status, BuyRequest.FULFILLED)
        self.client_for(self.farmer).post(f"/api/orders/{oid}/reject/")
        req.refresh_from_db()
        self.assertEqual(req.status, BuyRequest.OPEN)

    def test_order_against_someone_elses_or_wrong_crop_request_is_refused(self):
        lst = self.listing(qty=500)
        self.assertEqual(self.place(self.buyer, lst, 10, request=self.request_(buyer=self.buyer2)).status_code, 400)
        self.assertEqual(self.place(self.buyer, lst, 10, request=self.request_(crop=self.beans)).status_code, 400)
        lst.refresh_from_db()
        self.assertEqual(lst.quantity_kg, D("500.00"))  # failed orders must not leak reserved stock


class DatabaseUrlTests(SimpleTestCase):
    def test_parses_a_hosted_postgres_url(self):
        from config.settings import _database_from_url
        db = _database_from_url("postgresql://yt_user:p%40ss%2Fword@dpg-abc.frankfurt-postgres.render.com:5432/yt_db")
        self.assertEqual(db["NAME"], "yt_db")
        self.assertEqual(db["USER"], "yt_user")
        self.assertEqual(db["PASSWORD"], "p@ss/word")  # percent-encoded characters are decoded
        self.assertEqual((db["HOST"], db["PORT"]), ("dpg-abc.frankfurt-postgres.render.com", "5432"))
        self.assertEqual(db["ENGINE"], "django.db.backends.postgresql")

    def test_port_defaults_and_scheme_is_checked(self):
        from config.settings import _database_from_url
        self.assertEqual(_database_from_url("postgres://u:p@h/db")["PORT"], "5432")
        with self.assertRaises(Exception):
            _database_from_url("mysql://u:p@h/db")


class LoadCropsTests(TestCase):
    def test_is_idempotent(self):
        from django.core.management import call_command
        call_command("load_crops", verbosity=0)
        first = Crop.objects.count()
        call_command("load_crops", verbosity=0)
        self.assertEqual(Crop.objects.count(), first)
        self.assertGreaterEqual(first, 10)
