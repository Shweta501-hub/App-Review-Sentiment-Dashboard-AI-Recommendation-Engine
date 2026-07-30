const API_BASE = 'http://127.0.0.1:5000/api';

let sentimentChartInstance = null;
let aspectChartInstance = null;
let allReviewsData = [];

document.addEventListener('DOMContentLoaded', () => {
    fetchDashboardData();
    setupEventListeners();
});

function setupEventListeners() {
    // Modal events
    const modal = document.getElementById('add-review-modal');
    document.getElementById('btn-open-modal').addEventListener('click', () => modal.classList.add('active'));
    document.getElementById('btn-close-modal').addEventListener('click', () => modal.classList.remove('active'));
    document.getElementById('btn-cancel-modal').addEventListener('click', () => modal.classList.remove('active'));

    // Submit new review form
    document.getElementById('add-review-form').addEventListener('submit', handleNewReviewSubmit);

    // Run AI analysis button
    document.getElementById('btn-trigger-analysis').addEventListener('click', triggerAIAnalysis);

    // Filters
    document.getElementById('filter-aspect').addEventListener('change', filterReviewsTable);
    document.getElementById('filter-sentiment').addEventListener('change', filterReviewsTable);
}

async function fetchDashboardData() {
    await Promise.all([
        loadDashboardStats(),
        loadRecommendations(),
        loadReviewsList()
    ]);
}

async function loadDashboardStats() {
    try {
        const response = await fetch(`${API_BASE}/dashboard/stats`);
        const data = await response.json();

        if (response.ok) {
            document.getElementById('stat-total-reviews').innerText = data.total_reviews || 0;
            document.getElementById('stat-avg-rating').innerText = `${data.avg_rating || 0} / 5.0`;
            
            const nssElem = document.getElementById('stat-nss');
            nssElem.innerText = `${data.net_sentiment_score || 0}%`;
            nssElem.style.color = data.net_sentiment_score >= 0 ? 'var(--positive)' : 'var(--negative)';

            renderSentimentChart(data.sentiment_distribution);
            renderAspectChart(data.aspect_breakdown);
        }
    } catch (err) {
        console.error("Error loading stats:", err);
    }
}

async function loadRecommendations() {
    const container = document.getElementById('recommendations-container');
    try {
        const response = await fetch(`${API_BASE}/recommendations`);
        const data = await response.json();

        if (response.ok && data.recommendations) {
            document.getElementById('rec-count-badge').innerText = `${data.count} Insights`;
            document.getElementById('stat-urgent-issues').innerText = data.recommendations.filter(r => r.urgency_level === 'High').length;

            if (data.recommendations.length === 0) {
                container.innerHTML = `<p class="text-muted">No negative sentiment recommendations generated yet.</p>`;
                return;
            }

            container.innerHTML = data.recommendations.map(rec => {
                const levelClass = rec.urgency_level.toLowerCase();
                return `
                    <div class="rec-card ${levelClass}">
                        <div class="rec-header">
                            <span class="rec-aspect"><i class="fa-solid fa-layer-group"></i> ${rec.aspect_category}</span>
                            <span class="badge badge-${levelClass}">${rec.urgency_level} Urgency</span>
                        </div>
                        <div class="rec-body">
                            <p>${rec.actionable_recommendation}</p>
                        </div>
                        <div class="rec-footer">
                            <span>Negative Reviews: <strong>${rec.negative_count}</strong></span>
                            <span>Avg Rating: <strong>${rec.avg_rating} / 5</strong></span>
                            <span>Score: <strong>${rec.urgency_score}</strong></span>
                        </div>
                    </div>
                `;
            }).join('');
        }
    } catch (err) {
        container.innerHTML = `<p style="color:var(--negative)">Failed to load recommendations from server.</p>`;
    }
}

async function loadReviewsList() {
    const tbody = document.getElementById('reviews-table-body');
    try {
        const response = await fetch(`${API_BASE}/reviews`);
        const data = await response.json();

        if (response.ok && data.reviews) {
            allReviewsData = data.reviews;
            renderReviewsTable(allReviewsData);
        }
    } catch (err) {
        tbody.innerHTML = `<tr><td colspan="6" style="color:var(--negative)">Error fetching reviews feed.</td></tr>`;
    }
}

function renderReviewsTable(reviews) {
    const tbody = document.getElementById('reviews-table-body');
    if (reviews.length === 0) {
        tbody.innerHTML = `<tr><td colspan="6" class="text-center">No reviews found matching criteria.</td></tr>`;
        return;
    }

    tbody.innerHTML = reviews.map(r => {
        const stars = '★'.repeat(r.rating) + '☆'.repeat(5 - r.rating);
        const sentimentClass = r.sentiment_label.toLowerCase();
        return `
            <tr>
                <td><span class="rating-stars">${stars}</span></td>
                <td>${escapeHtml(r.review_text)}</td>
                <td><span class="badge badge-purple">${r.aspect_category}</span></td>
                <td><span class="sentiment-badge ${sentimentClass}">${r.sentiment_label}</span></td>
                <td><code>${r.app_version}</code></td>
                <td>${escapeHtml(r.author || 'Anonymous')}</td>
            </tr>
        `;
    }).join('');
}

function filterReviewsTable() {
    const selectedAspect = document.getElementById('filter-aspect').value;
    const selectedSentiment = document.getElementById('filter-sentiment').value;

    const filtered = allReviewsData.filter(r => {
        const matchAspect = selectedAspect === 'ALL' || r.aspect_category === selectedAspect;
        const matchSentiment = selectedSentiment === 'ALL' || r.sentiment_label === selectedSentiment;
        return matchAspect && matchSentiment;
    });

    renderReviewsTable(filtered);
}

async function handleNewReviewSubmit(e) {
    e.preventDefault();

    const payload = {
        author: document.getElementById('review-author').value.trim(),
        rating: parseInt(document.getElementById('review-rating').value),
        app_version: document.getElementById('review-version').value.trim(),
        review_text: document.getElementById('review-text').value.trim()
    };

    try {
        const response = await fetch(`${API_BASE}/reviews`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (response.ok) {
            document.getElementById('add-review-modal').classList.remove('active');
            document.getElementById('add-review-form').reset();

            // Trigger AI analysis on newly added review
            await triggerAIAnalysis();
        }
    } catch (err) {
        alert("Failed to submit review. Ensure Flask backend is running.");
    }
}

async function triggerAIAnalysis() {
    const btn = document.getElementById('btn-trigger-analysis');
    btn.innerHTML = `<i class="fa-solid fa-circle-notch fa-spin"></i> Analyzing...`;
    btn.disabled = true;

    try {
        const response = await fetch(`${API_BASE}/analyze`, { method: 'POST' });
        if (response.ok) {
            await fetchDashboardData();
        }
    } catch (err) {
        alert("Failed to trigger analysis pipeline.");
    } finally {
        btn.innerHTML = `<i class="fa-solid fa-rotate-right"></i> Run AI Analysis`;
        btn.disabled = false;
    }
}

function renderSentimentChart(dist) {
    const ctx = document.getElementById('sentimentChart').getContext('2d');
    
    if (sentimentChartInstance) sentimentChartInstance.destroy();

    const pos = dist ? dist.positive : 0;
    const neg = dist ? dist.negative : 0;
    const neu = dist ? dist.neutral : 0;

    sentimentChartInstance = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['Positive', 'Negative', 'Neutral'],
            datasets: [{
                data: [pos, neg, neu],
                backgroundColor: ['#10b981', '#ef4444', '#f59e0b'],
                borderWidth: 0
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { position: 'bottom', labels: { color: '#94a3b8', font: { family: 'Outfit' } } }
            }
        }
    });
}

function renderAspectChart(aspects) {
    const ctx = document.getElementById('aspectChart').getContext('2d');

    if (aspectChartInstance) aspectChartInstance.destroy();

    const labels = aspects ? aspects.map(a => a.aspect) : [];
    const counts = aspects ? aspects.map(a => a.count) : [];

    aspectChartInstance = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: 'Complaint Count',
                data: counts,
                backgroundColor: '#6366f1',
                borderRadius: 6
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: { ticks: { color: '#94a3b8' }, grid: { display: false } },
                y: { ticks: { color: '#94a3b8' }, grid: { color: '#334155' } }
            },
            plugins: {
                legend: { display: false }
            }
        }
    });
}

function escapeHtml(str) {
    return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
