import os
import sys

# Ensure project root is in sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy.orm import Session
from sqlalchemy import func
from database.db import SessionLocal, init_db
from database.models import Review, SentimentAnalysis, Recommendation


def generate_recommendations(db: Session = None):
    """Aggregate negative sentiment data, calculate urgency metrics, and store recommendations."""
    close_session = False
    if db is None:
        db = SessionLocal()
        close_session = True

    try:
        # Clear existing recommendations to regenerate fresh insights
        db.query(Recommendation).delete()
        
        # Query aggregate metrics for Negative reviews grouped by aspect category
        results = (
            db.query(
                SentimentAnalysis.aspect_category,
                func.count(SentimentAnalysis.id).label('negative_count'),
                func.avg(Review.rating).label('avg_rating')
            )
            .join(Review, SentimentAnalysis.review_id == Review.id)
            .filter(SentimentAnalysis.sentiment_label == 'Negative')
            .group_by(SentimentAnalysis.aspect_category)
            .all()
        )

        if not results:
            print("No negative reviews found to generate recommendations.")
            if close_session:
                db.close()
            return 0

        recs_to_add = []
        for aspect, neg_count, avg_rat in results:
            avg_rating_val = round(float(avg_rat or 1.0), 2)
            urgency_score = round(neg_count * (5.0 - avg_rating_val), 2)

            # Determine urgency level
            if urgency_score >= 10.0:
                urgency_level = "High"
            elif urgency_score >= 5.0:
                urgency_level = "Medium"
            else:
                urgency_level = "Low"

            # Formulate targeted action item text
            if aspect == "Bug / Crash":
                action = f"CRITICAL FIX: Address app crashes and stability issues reported in {neg_count} reviews (Avg rating: {avg_rating_val}/5)."
            elif aspect == "Performance / Speed":
                action = f"OPTIMIZE PERFORMANCE: Resolve latency, slow loading, and battery drain complaints ({neg_count} reviews)."
            elif aspect == "UI / UX":
                action = f"REDESIGN UI/UX: Simplify interface layout and touch target sizes based on {neg_count} negative user complaints."
            elif aspect == "Pricing / Subscription":
                action = f"REVIEW PRICING MODEL: Address user dissatisfaction regarding subscription cost and value transparency ({neg_count} reviews)."
            else:
                action = f"INVESTIGATE GENERAL ISSUES: Review user feedback in '{aspect}' category to improve satisfaction."

            rec = Recommendation(
                aspect_category=aspect,
                urgency_level=urgency_level,
                negative_count=neg_count,
                avg_rating=avg_rating_val,
                urgency_score=urgency_score,
                actionable_recommendation=action
            )
            recs_to_add.append(rec)

        # Sort recommendations by urgency score descending before adding
        recs_to_add.sort(key=lambda r: r.urgency_score, reverse=True)
        db.add_all(recs_to_add)
        db.commit()

        print(f"Generated {len(recs_to_add)} prioritized recommendations.")
        return len(recs_to_add)
    except Exception as e:
        db.rollback()
        print(f"Error generating recommendations: {e}")
        return 0
    finally:
        if close_session:
            db.close()

if __name__ == "__main__":
    init_db()
    generate_recommendations()
