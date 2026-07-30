import sys
import os
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database.db import init_db, SessionLocal
from database.models import Review, SentimentAnalysis, Recommendation
from models.bert_sentiment import process_unprocessed_reviews
from models.recommender import generate_recommendations

WEB_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "web"))

app = Flask(__name__, static_folder=WEB_DIR, static_url_path="")
CORS(app)  # Enable Cross-Origin Requests

# Ensure database tables exist at startup
init_db()

@app.route('/', methods=['GET'])
def index():
    """Serve Dashboard Web UI."""
    return send_from_directory(WEB_DIR, 'index.html')

@app.route('/<path:path>', methods=['GET'])
def static_proxy(path):
    """Serve static CSS/JS/assets."""
    return send_from_directory(WEB_DIR, path)

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify({"status": "healthy", "service": "App Review Sentiment API"}), 200

@app.route('/api/reviews', methods=['GET'])
def get_reviews():
    """Fetch all app reviews with their sentiment and aspect tags."""
    db = SessionLocal()
    try:
        reviews = db.query(Review).all()
        results = []
        for r in reviews:
            item = {
                "id": r.id,
                "app_name": r.app_name,
                "app_version": r.app_version,
                "author": r.author,
                "review_text": r.review_text,
                "cleaned_text": r.cleaned_text,
                "rating": r.rating,
                "review_date": r.review_date.strftime("%Y-%m-%d %H:%M:%S") if r.review_date else None,
                "is_processed": r.is_processed,
                "sentiment_label": r.sentiment.sentiment_label if r.sentiment else "Pending",
                "sentiment_score": r.sentiment.sentiment_score if r.sentiment else None,
                "aspect_category": r.sentiment.aspect_category if r.sentiment else "Pending"
            }
            results.append(item)
        return jsonify({"count": len(results), "reviews": results}), 200
    finally:
        db.close()

@app.route('/api/reviews', methods=['POST'])
def add_review():
    """Add a new review to the database."""
    data = request.get_json()
    if not data or 'review_text' not in data or 'rating' not in data:
        return jsonify({"error": "Fields 'review_text' and 'rating' are required."}), 400

    db = SessionLocal()
    try:
        new_rev = Review(
            app_name=data.get('app_name', 'ProductivitySuite'),
            app_version=data.get('app_version', 'v2.4.0'),
            author=data.get('author', 'User'),
            review_text=data['review_text'],
            cleaned_text=data['review_text'].strip(),
            rating=int(data['rating']),
            is_processed=False
        )
        db.add(new_rev)
        db.commit()
        db.refresh(new_rev)
        return jsonify({"message": "Review added successfully", "id": new_rev.id}), 201
    except Exception as e:
        db.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()

@app.route('/api/analyze', methods=['POST'])
def trigger_analysis():
    """Trigger sentiment analysis and recommendation generation."""
    db = SessionLocal()
    try:
        processed_count = process_unprocessed_reviews(db)
        recs_count = generate_recommendations(db)
        return jsonify({
            "message": "Analysis pipeline executed successfully",
            "reviews_processed": processed_count,
            "recommendations_generated": recs_count
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()

@app.route('/api/dashboard/stats', methods=['GET'])
def get_dashboard_stats():
    """Return aggregated stats for dashboard."""
    db = SessionLocal()
    try:
        total_reviews = db.query(Review).count()
        if total_reviews == 0:
            return jsonify({"total_reviews": 0, "message": "No reviews available"}), 200

        # Sentiment Distribution
        pos_count = db.query(SentimentAnalysis).filter(SentimentAnalysis.sentiment_label == 'Positive').count()
        neg_count = db.query(SentimentAnalysis).filter(SentimentAnalysis.sentiment_label == 'Negative').count()
        neu_count = db.query(SentimentAnalysis).filter(SentimentAnalysis.sentiment_label == 'Neutral').count()

        # Average Rating
        avg_rating = db.query(Review).with_entities(Review.rating).all()
        ratings = [r[0] for r in avg_rating if r[0] is not None]
        avg_rating_val = round(sum(ratings) / len(ratings), 2) if ratings else 0.0

        # Net Sentiment Score (NSS = % Pos - % Neg)
        nss = round(((pos_count - neg_count) / total_reviews) * 100, 2) if total_reviews > 0 else 0.0

        # Aspect breakdown
        aspects_query = db.query(SentimentAnalysis.aspect_category, Review.rating)\
            .join(Review, SentimentAnalysis.review_id == Review.id).all()
        
        aspect_summary = {}
        for category, rating in aspects_query:
            if category not in aspect_summary:
                aspect_summary[category] = {"count": 0, "total_rating": 0}
            aspect_summary[category]["count"] += 1
            aspect_summary[category]["total_rating"] += rating

        aspects_formatted = [
            {
                "aspect": cat,
                "count": info["count"],
                "avg_rating": round(info["total_rating"] / info["count"], 2)
            }
            for cat, info in aspect_summary.items()
        ]

        return jsonify({
            "total_reviews": total_reviews,
            "avg_rating": avg_rating_val,
            "net_sentiment_score": nss,
            "sentiment_distribution": {
                "positive": pos_count,
                "negative": neg_count,
                "neutral": neu_count
            },
            "aspect_breakdown": aspects_formatted
        }), 200
    finally:
        db.close()

@app.route('/api/recommendations', methods=['GET'])
def get_recommendations():
    """Fetch actionable recommendations ordered by urgency score."""
    db = SessionLocal()
    try:
        recs = db.query(Recommendation).order_by(Recommendation.urgency_score.desc()).all()
        results = [
            {
                "id": r.id,
                "aspect_category": r.aspect_category,
                "urgency_level": r.urgency_level,
                "negative_count": r.negative_count,
                "avg_rating": r.avg_rating,
                "urgency_score": r.urgency_score,
                "actionable_recommendation": r.actionable_recommendation,
                "created_at": r.created_at.strftime("%Y-%m-%d %H:%M:%S") if r.created_at else None
            }
            for r in recs
        ]
        return jsonify({"count": len(results), "recommendations": results}), 200
    finally:
        db.close()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
