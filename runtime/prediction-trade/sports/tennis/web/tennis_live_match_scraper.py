import asyncio
import json
import logging
import os
from typing import Dict, Optional
from playwright.async_api import async_playwright

# Setup lightweight logging for background execution
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"

async def scrape_live_match(player1: str, player2: Optional[str] = None) -> Dict:
    """
    Scrapes a live tennis match from Sofascore or network streams to extract
    features required by the Model Version 4.0 framework.
    
    :param player1: Name of the first player (Mandatory)
    :param player2: Name of the second player (Optional)
    :return: A cleaned dictionary mapped to the prediction model requirements
    """
    p1_query = player1.lower().strip()
    p2_query = player2.lower().strip() if player2 else None
    
    match_data = {
        "status": "No Match Found",
        "pre_match_favorite": None,
        "implied_probability_p1": None,
        "scenario_type": "Unknown",
        "set_1_winner": None,
        "set_1_margin": None,
        "current_set": None,
        "serving": None,
        "current_games": "0:0",
        "current_points": "0:0",
        "break_point": "NO",
        "double_break_detected": "NO",
        "is_consolidation_game": "NO",
        "stay_in_set_pressure": "NO"
    }

    async with async_playwright() as p:
        # Launching headless mode for maximum execution speed as a backend utility
        browser = await p.chromium.launch(headless=True)
        
        # Inject standard desktop sizes and headers to avoid bot detection flags
        context = await browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1280, "height": 720}
        )
        
        page = await context.new_page()
        
        # Intercepting background API calls made by the SPA framework to grab clean JSON data
        target_match_id = None
        api_data = {}

        async def handle_response(response):
            if "api/v1/sport/tennis/events/live" in response.url:
                try:
                    text = await response.text()
                    api_data['live_list'] = json.loads(text)
                except Exception:
                    pass

        page.on("response", handle_response)

        try:
            # Route to live tennis events directly
            logger.info("Navigating to live tennis directory...")
            await page.goto("https://www.sofascore.com/tennis/in-progress", wait_until="networkidle", timeout=30000)
            
            if 'live_list' not in api_data or 'events' not in api_data['live_list']:
                # Fallback backup option: Wait explicitly for standard page components if network tracking stutters
                await page.wait_for_selector("[data-testid='event_cell']", timeout=15000)
                logger.warning("Falling back to DOM tracking strategy...")
                
            # Parse the intercepted API package for matching names
            events = api_data.get('live_list', {}).get('events', [])
            target_event = None
            
            for event in events:
                home_name = event.get('homeTeam', {}).get('name', '').lower()
                away_name = event.get('awayTeam', {}).get('name', '').lower()
                
                # Verify match criteria match parameters
                if p1_query in home_name or p1_query in away_name:
                    if p2_query:
                        if p2_query in home_name or p2_query in away_name:
                            target_event = event
                            break
                    else:
                        target_event = event
                        break
            
            if not target_event:
                logger.info(f"Match for {player1} vs {player2} not found on main target. Shifting source routing...")
                # Here you can implement automated navigation to an alternate open source line (e.g., flashscore)
                await browser.close()
                return match_data

            # ----------------------------------------------------
            # DATA EXTRACTION & FIELD SANITIZATION FOR MODEL V4.0
            # ----------------------------------------------------
            match_data["status"] = "In-Progress"
            
            # 1. Ranks and Scenario Identification
            p1_rank = target_event.get('homeTeam', {}).get('ranking', 999)
            p2_rank = target_event.get('awayTeam', {}).get('ranking', 999)
            
            if p1_rank <= 10 or p2_rank <= 10:
                match_data["scenario_type"] = "Scenario 1 (Elite)"
            else:
                match_data["scenario_type"] = "Scenario 2 (Group Parity)"
                
            # 2. Extract Live Odds / Implied Probabilities
            # sofa uses 'hasOdds' or embeds dynamic market vectors
            match_data["pre_match_favorite"] = "A" if p1_rank < p2_rank else "B"
            
            # 3. Score Parsing
            scores = target_event.get('status', {})
            home_score = target_event.get('homeScore', {})
            away_score = target_event.get('awayScore', {})
            
            h_set1 = home_score.get('period1', 0)
            a_set1 = away_score.get('period1', 0)
            
            current_period = home_score.get('current', 1)
            match_data["current_set"] = current_period
            
            if current_period > 1:
                match_data["set_1_winner"] = "A" if h_set1 > a_set1 else "B"
                match_data["set_1_margin"] = abs(h_set1 - a_set1)
            
            # 4. Micro-state Point Combinations (Real-time Frame)
            h_games = home_score.get('period{}'.format(current_period), 0)
            a_games = away_score.get('period{}'.format(current_period), 0)
            match_data["current_games"] = f"{h_games}:{a_games}"
            
            # Extract point-by-point tracking arrays safely
            h_points = target_event.get('homeScore', {}).get('point', '0')
            a_points = target_event.get('awayScore', {}).get('point', '0')
            match_data["current_points"] = f"{h_points}:{a_points}"
            
            # 5. Serving Indicators
            # 1 indicates home serving, 2 indicates away serving
            server_indicator = target_event.get('status', {}).get('serving', 1)
            match_data["serving"] = "A" if server_indicator == 1 else "B"
            
            # 6. Break Point Detection Rules
            serv = match_data["serving"]
            if (serv == "A" and a_points in ["40", "A"]) and h_points != "A":
                match_data["break_point"] = "YES"
            elif (serv == "B" and h_points in ["40", "A"]) and a_points != "A":
                match_data["break_point"] = "YES"
                
            # 7. Model V4.0 Logic Triggers
            # Pressure Stay Game Tracker (4-5 or 5-6)
            if (h_games == 4 and a_games == 5 and serv == "A") or (h_games == 5 and a_games == 4 and serv == "B"):
                match_data["stay_in_set_pressure"] = "YES"
                
            logger.info("Successfully vectorized live tennis match telemetry.")

        except Exception as e:
            logger.error(f"Execution Error during runtime capture: {str(e)}")
        finally:
            await browser.close()
            
    return match_data

async def get_live_statuses() -> list:
    """
    Fetch the status of ALL live tennis matches in ONE browser session.
    Returns [{home, away, status, desc}, ...] where ``status`` is the SofaScore
    status type lowercased ("inprogress", "interrupted", "suspended",
    "finished", "notstarted", …) and ``desc`` is the human label
    (e.g. "2nd set").  Returns [] on any failure (callers should fail open).
    """
    out: list = []
    headless = os.getenv("SOFA_HEADLESS", "TRUE").strip().upper() != "FALSE"
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"])
        context = await browser.new_context(
            user_agent=USER_AGENT, viewport={"width": 1366, "height": 900}, locale="en-US")
        page = await context.new_page()
        api: dict = {}

        async def handle(resp):
            if "sport/tennis/events/live" in resp.url:
                try:
                    api["x"] = json.loads(await resp.text())
                except Exception:
                    pass

        page.on("response", handle)
        try:
            await page.goto("https://www.sofascore.com/tennis/in-progress",
                            wait_until="domcontentloaded", timeout=30000)
            for _ in range(16):                      # wait for the intercepted live feed
                if "x" in api:
                    break
                await page.wait_for_timeout(500)
            events = (api.get("x", {}) or {}).get("events", [])
            if not events:                           # fallback: fetch in-page (auth context)
                try:
                    body = await page.evaluate(
                        "async () => { const r = await fetch("
                        "'/api/v1/sport/tennis/events/live', "
                        "{headers:{'Accept':'application/json'}}); "
                        "return r.ok ? await r.text() : ''; }")
                    if body:
                        events = (json.loads(body) or {}).get("events", [])
                except Exception:
                    pass
            for e in events:
                st = e.get("status", {}) or {}
                out.append({
                    "home": (e.get("homeTeam", {}) or {}).get("name", ""),
                    "away": (e.get("awayTeam", {}) or {}).get("name", ""),
                    "status": str(st.get("type", "")).lower(),
                    "desc": st.get("description", ""),
                })
            logger.info(f"get_live_statuses: {len(out)} live matches")
        except Exception as ex:
            logger.error(f"get_live_statuses error: {str(ex)}")
        finally:
            await browser.close()
    return out


# Simple programmatic harness execution example
if __name__ == "__main__":
    # Example execution: Search for Carlos Alcaraz live match
    result = asyncio.run(scrape_live_match("Alcaraz"))
    print(json.dumps(result, indent=4))