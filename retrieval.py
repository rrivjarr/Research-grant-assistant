"""Hybrid retrieval: TF-IDF semantic-style scoring + metadata filters + re-ranking."""
import datetime as dt
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from ingest import load_notices, chunk

class Index:
    def __init__(self, notices=None):
        self.notices = notices or load_notices()
        self.by_id = {n.id: n for n in self.notices}
        self.chunks = [c for n in self.notices for c in chunk(n)]
        self.vec = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), sublinear_tf=True)
        self.matrix = self.vec.fit_transform(c["text"] for c in self.chunks)

    def search(self, query, today=None, agency=None, include_expired=False, top_k=5):
        today = today or dt.date.today()
        sims = cosine_similarity(self.vec.transform([query]), self.matrix)[0]
        best = {}
        for c, s in zip(self.chunks, sims):
            cur = best.get(c["notice_id"])
            if cur is None or s > cur[0]:
                best[c["notice_id"]] = (s, c["section"])
        results = []
        for nid, (score, section) in best.items():
            n = self.by_id[nid]
            status = n.status(today)
            if agency and agency.lower() not in n.agency.lower():
                continue
            if status == "EXPIRED" and not include_expired:
                continue
            # re-rank: small boost for open calls with a real deadline
            rerank = score + (0.05 if status == "OPEN" else 0.0)
            if score > 0:
                results.append({"notice": n, "score": round(float(score), 3),
                                "final": round(float(rerank), 3), "matched": section, "status": status})
        results.sort(key=lambda r: r["final"], reverse=True)
        return results[:top_k]
