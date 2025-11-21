from flask import Flask

app = Flask(__name__)

@app.route('/')
def home():
    return 'Hello, World!'

@app.route("/ranking", methods=["POST"])
def ranking():

    body = request.get_json()
    if not body or "eventCode" not in body:
        return jsonify({"error": "eventCode requerido"}), 400

    eventCode = body["eventCode"]

    try:
        # -------------------------
        # 1️⃣ Cargar datos de Supabase (sin pandas)
        # -------------------------
        pits = supabase.table("pits").select("team_number, region, cycle_number, artifacts_number, check1").execute().data or []
        matches = supabase.table("matches").select(
            "team_number,regional,check_inicio,count_motiv,"
            "count_in_cage_auto,count_in_cage_teleop,count_rp,"
            "check_scoring,count_in_cage_endgame,check_full_park"
        ).execute().data or []

        if not pits or not matches:
            return jsonify([])

        # Index O(1)
        pits_index = {(p["team_number"], p["region"]): p for p in pits}

        # -------------------------
        # 2️⃣ Unir datos mínimamente
        # -------------------------
        unidos = []
        for m in matches:
            key = (m["team_number"], m["regional"])
            unidos.append({**m, **pits_index.get(key, {})})

        # -------------------------
        # 3️⃣ Calcular score ligero
        # -------------------------
        score_cols = [
            "check_inicio", "count_motiv",
            "count_in_cage_auto", "count_in_cage_teleop",
            "count_rp", "check_scoring",
            "count_in_cage_endgame", "check_full_park",
            "cycle_number", "artifacts_number", "check1"
        ]

        for row in unidos:
            row["score"] = sum((row.get(c) or 0) for c in score_cols)

        # -------------------------
        # 4️⃣ Agrupar por equipo (compacto)
        # -------------------------
        teams = {}
        for row in unidos:
            t = row["team_number"]

            if t not in teams:
                teams[t] = {
                    "team_number": t,
                    "score_sum": 0,
                    "count": 0,
                    "auto": 0,
                    "tele": 0
                }

            teams[t]["score_sum"] += row["score"]
            teams[t]["count"] += 1
            teams[t]["auto"] += row.get("count_in_cage_auto", 0)
            teams[t]["tele"] += row.get("count_in_cage_teleop", 0)

        # -------------------------
        # 5️⃣ Obtener ranking FTC 1 sola vez
        # -------------------------
        try:
            url = f"http://ftc-api.firstinspires.org/v2.0/2024/rankings/{eventCode}"
            r = requests.get(url, auth=HTTPBasicAuth(
                "crisesv4",
                "E936A6EC-14B0-4904-8DF4-E4916CA4E9BB"
            ))
            ranking_api = {item["teamNumber"]: item.get("rank") for item in r.json().get("rankings", [])}
        except:
            ranking_api = {}

        # -------------------------
        # 6️⃣ Compute alliance_score (súper reducido)
        # -------------------------
        results = []
        for t, data in teams.items():
            avg_score = data["score_sum"] / data["count"]

            eff = (data["auto"] + data["tele"]) / (avg_score + 1)
            frs = 1 / ranking_api.get(t, 9999)

            alliance_score = avg_score * 0.7 + eff * 0.2 + frs * 0.1

            results.append({
                "team_number": t,
                "score": round(avg_score, 2),
                "alliance_score": round(alliance_score, 3),
                "ftc_rank": ranking_api.get(t)
            })

        # -------------------------
        # 7️⃣ Orden final
        # -------------------------
        results.sort(key=lambda x: x["alliance_score"], reverse=True)
        return jsonify(results)

    except Exception as e:
        return jsonify({"error": str(e)}), 500
