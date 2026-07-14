import json

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count, Prefetch
from django.http import JsonResponse, StreamingHttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_POST

from django.utils.http import url_has_allowed_host_and_scheme

from core.hybrid_chat import ChatResponse, process_chat, stream_chat
from products.models import Product, Review, ScrapedListing
from products.price_utils import display_listing_for_product
from products.availability import available_first


def _review_context(limit=6):
    """Published reviews plus aggregate rating info for the testimonials UI."""
    published = Review.objects.filter(is_published=True)
    agg = published.aggregate(avg=Avg("rating"), total=Count("id"))
    avg = agg["avg"] or 0
    return {
        "reviews": list(published[:limit]),
        "reviews_avg": round(avg, 1),
        "reviews_count": agg["total"] or 0,
    }


def home(request):
    popular_products = list(
        available_first(
            Product.objects.prefetch_related(
                Prefetch("listings", queryset=ScrapedListing.objects.select_related("store"))
            )
        )[:6]
    )
    popular_cards = [
        {"product": product, "best_listing": display_listing_for_product(product)}
        for product in popular_products
    ]
    context = {
        "popular_products": popular_products,
        "popular_cards": popular_cards,
    }
    context.update(_review_context())
    return render(request, "core/home.html", context)


@login_required
def about(request):
    return render(request, "core/about.html", _review_context(limit=6))


@login_required
@require_POST
def add_review(request):
    body = (request.POST.get("body") or "").strip()
    role = (request.POST.get("author_role") or "").strip()[:80]
    try:
        rating = int(request.POST.get("rating") or 5)
    except (TypeError, ValueError):
        rating = 5
    rating = max(1, min(5, rating))

    if not body:
        messages.error(request, "Please write a short review before submitting.")
    else:
        author_name = (request.user.get_full_name() or request.user.username).strip()
        Review.objects.create(
            user=request.user,
            author_name=author_name or request.user.username,
            author_role=role or "PriceVerse User",
            rating=rating,
            body=body[:1000],
            is_published=True,
            is_sample=False,
        )
        messages.success(request, "Thanks for your review! It's now live on the site.")

    redirect_to = request.POST.get("next") or (reverse("core:home") + "#reviews")
    if not url_has_allowed_host_and_scheme(
        redirect_to,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        redirect_to = reverse("core:home") + "#reviews"
    return redirect(redirect_to)


def _save_chat_history(request, user_msg: str, reply: str) -> None:
    history = request.session.get("chat_history", [])
    history.append({"role": "user", "content": user_msg})
    history.append({"role": "assistant", "content": reply})
    max_turns = int(getattr(settings, "CHAT_SESSION_HISTORY_TURNS", 12) or 12)
    request.session["chat_history"] = history[-max_turns:]
    request.session.modified = True


@login_required
@require_POST
@csrf_protect
def chat_api(request):
    try:
        data = json.loads(request.body.decode("utf-8"))
    except Exception:
        data = {}

    user_msg = (data.get("message") or "").strip()
    if not user_msg:
        return JsonResponse({"reply": "Please type a message."})

    history = request.session.get("chat_history", [])
    result = process_chat(user_msg, history=history)
    _save_chat_history(request, user_msg, result.text)

    return JsonResponse({"reply": result.text, "timing": result.timing.as_dict()})


@login_required
@require_POST
@csrf_protect
def chat_stream_api(request):
    try:
        data = json.loads(request.body.decode("utf-8"))
    except Exception:
        data = {}

    user_msg = (data.get("message") or "").strip()
    if not user_msg:
        return JsonResponse({"reply": "Please type a message."})

    history = request.session.get("chat_history", [])

    def event_stream():
        final: ChatResponse | None = None
        yield f"data: {json.dumps({'type': 'start'})}\n\n"
        for item in stream_chat(user_msg, history=history):
            if isinstance(item, ChatResponse):
                final = item
                continue
            yield f"data: {json.dumps({'type': 'chunk', 'content': item})}\n\n"

        if final is None:
            from core.chat_perf import PipelineTiming

            final = ChatResponse(text="Sorry, no response was generated.", timing=PipelineTiming())
        _save_chat_history(request, user_msg, final.text)
        payload = {"type": "done", "reply": final.text}
        if final.timing:
            payload["timing"] = final.timing.as_dict()
        yield f"data: {json.dumps(payload)}\n\n"

    response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response

