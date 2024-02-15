import os
import json
import random
import requests
import threading
import pandas as pd
from queue import Queue
from flask import Flask
from flask_cors import CORS
from flask import send_file
from datetime import datetime
from bs4 import BeautifulSoup
from collections import namedtuple
from urllib.parse import urlencode, quote
from playwright.sync_api import sync_playwright

# Default Configs
configs = {
    "Lang": "en",
    "Locale": "en-US",
    "TimeZone": "America/Chicago",
    "RndDeviceID": str(random.randint(10 ** 18, 10 ** 19 - 1)),
    "DefaultURL": "https://www.tiktok.com/@redbull/video/7285391124246646049",
    # "UserAgent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.6099.28 Safari/537.36 Edg/120.0.6099.28",
    # "UserAgent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "UserAgent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
}

# Common Headers for APIs
headers = {
    "Origin": "https://www.tiktok.com/",
    "Referer": "https://www.tiktok.com/",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    'Cache-Control': 'no-cache',
    'Pragma': 'no-cache',
    'Authority': 'www.tiktok.com',
    "User-Agent": configs["UserAgent"],
}

# Browser session state
session = namedtuple('session', ['playwright', 'browser', 'context', 'page', 'info'])
instance = {
    "TaskLogs": '',
    "TaskRunning": False,
}

# SERVER SETUP
server_host = '0.0.0.0'
server_port = '8000'

app = Flask(__name__)
CORS(app)

# Utility Functions
isExist = os.path.exists
joinPath = os.path.join
projectDir = os.path.dirname(__file__)


def createDir(path, override=False):
    if override or not isExist(path):
        os.mkdir(path)
        return True
    return False


def threaded(f, daemon=False):
    def wrapped_f(q, *args, **kwargs):
        """this function calls the decorated function and puts the
        result in a queue"""
        ret = f(*args, **kwargs)
        q.put(ret)

    def wrap(*args, **kwargs):
        """this is the function returned from the decorator. It fires off
        wrapped_f in a new thread and returns the thread object with
        the result queue attached"""

        q = Queue()

        t = threading.Thread(target=wrapped_f, args=(q,) + args, kwargs=kwargs)
        t.daemon = daemon
        t.start()
        t.result_queue = q
        return t

    return wrap


def get_params():
    return {
        "aid": "1988",
        "app_language": configs["Lang"],
        "app_name": "tiktok_web",
        "browser_language": session.info["browser_language"],
        "browser_name": "Mozilla",
        "browser_online": "true",
        "browser_platform": session.info["browser_platform"],
        "browser_version": session.info["user_agent"],
        "channel": "tiktok_web",
        "cookie_enabled": "true",
        "device_id": configs["RndDeviceID"],
        "device_platform": "web_pc",
        "focus_state": "true",
        "from_page": "user",
        "history_len": session.info["history"],
        "is_fullscreen": "false",
        "is_page_visible": "true",
        "language": configs["Lang"],
        "os": session.info["platform"],
        "priority_region": "",
        "referer": "",
        "region": "US",
        "screen_height": session.info["screen_height"],
        "screen_width": session.info["screen_width"],
        "tz_name": configs["TimeZone"],
        "webcast_language": configs["Lang"],
    }


def fetch_data(url, headers):
    headers_js = json.dumps(headers)
    js_fetch = f"""
        () => {{
            return new Promise((resolve, reject) => {{
                fetch('{url}', {{ method: 'GET', headers: {headers_js} }})
                    .then(response => response.text())
                    .then(data => resolve(data))
                    .catch(error => reject(error.message));
            }});
        }}
    """
    result = session.page.evaluate(js_fetch)
    try:
        return json.loads(result)
    except ValueError:
        return result


def encode_url(base, params):
    return f"{base}?{urlencode(params, quote_via=quote)}"


def extract_stateinfo(content):
    soup = BeautifulSoup(content, 'html.parser')
    res = {}
    sigi_data = soup.find_all('script', {'id': 'SIGI_STATE'})
    if len(sigi_data) > 0:
        js_state = sigi_data[0]
        unescaped = js_state.text.replace("//", "/")
        res.update(json.loads(unescaped))
    hydra_data = soup.find_all('script', {'id': '__UNIVERSAL_DATA_FOR_REHYDRATION__'})
    if len(hydra_data) > 0:
        js_state = hydra_data[0]
        # js_state.text.encode('utf-8').decode('unicode_escape'), Corrupts the non-Ascii characters
        unescaped = js_state.text.replace("//", "/")
        unescaped = json.loads(unescaped)
        if "__DEFAULT_SCOPE__" in unescaped:
            res.update(unescaped)
    return res


def fetch_recommenations(count=10):
    base_url = "https://www.tiktok.com/api/recommend/item_list/"

    params = get_params()
    params["from_page"] = "fyp"
    params["count"] = 30

    # Max cap for now
    if count > 100:
        count = 100

    res = []
    found = 0

    while found < count:
        result = fetch_data(encode_url(base_url, params), headers)

        if 'itemList' not in result:
            break

        for t in result.get("itemList", []):
            res.append(t)
            found += 1

        if not result.get("hasMore", False):
            return res

        count -= found

    return res[:count]


def fetch_challenge_info(challenge="fashion"):
    base_url = "https://www.tiktok.com/api/challenge/detail/"

    params = get_params()
    params["from_page"] = "hashtag"
    params["challengeName"] = challenge

    result = fetch_data(encode_url(base_url, params), headers)
    if ("challengeInfo" not in result) or result["statusCode"] != 0:
        return None

    return result["challengeInfo"]


def fetch_tags_posts(hashtag="fashion", count=30):
    tag_data = fetch_challenge_info(hashtag)

    if not tag_data or "challenge" not in tag_data:
        return None

    tag_data = tag_data["challenge"]

    base_url = "https://www.tiktok.com/api/challenge/item_list/"

    params = get_params()
    params["challengeID"] = tag_data["id"]
    params["coverFormat"] = "2"
    params["cursor"] = "0"
    params["count"] = 30

    res = []
    found = 0

    while found < count:
        result = fetch_data(encode_url(base_url, params), headers)

        if ("cursor" not in result and "itemList" not in result) or result["statusCode"] != 0:
            break

        for t in result.get("itemList", []):
            res.append(t)
            found += 1

        if not result.get("hasMore", False):
            return res

        params["cursor"] = result["cursor"]

    return res[:count]


def get_user_info(hashtag="redbull"):
    user_url = "https://www.tiktok.com/@{}".format(hashtag)

    r = requests.get(user_url, headers=headers)
    if r.status_code != 200:
        return None

    data = extract_stateinfo(r.content)
    if "webapp.user-detail" in data:
        return data["webapp.user-detail"]
    return None


def get_comments_info(user="redbull", post="7285391124246646049"):
    post_url = "https://www.tiktok.com/@{}/video/{}".format(user, post)

    r = requests.get(post_url, headers=headers)
    if r.status_code != 200:
        return None

    data = extract_stateinfo(r.content)
    if "MobileSharingComment" in data:
        return data["MobileSharingComment"]
    return None


def fetch_search_suggest(keyword="fashion"):
    base_url = "https://www.tiktok.com/api/search/general/sug/"

    params = get_params()
    params["from_page"] = "search"
    params["keyword"] = keyword

    result = fetch_data(encode_url(base_url, params), headers)
    if ("sug_list" not in result) or result["status_code"] != 0:
        return None

    return result["sug_list"]


def fetch_search(keyword="fashion", count=10):
    obj_type = "user"
    base_url = f"https://www.tiktok.com/api/search/{obj_type}/full/"

    params = get_params()
    params["cursor"] = "0"
    params["count"] = 20
    params["from_page"] = "search"
    params["keyword"] = keyword
    params["root_referer"] = configs["DefaultURL"]
    params["web_search_code"] = """{"tiktok":{"client_params_x":{"search_engine":
    {"ies_mt_user_live_video_card_use_libra":1,"mt_search_general_user_live_card":1}},"search_server":{}}}"""

    res = []
    found = 0

    while found < count:
        result = fetch_data(encode_url(base_url, params), headers)
        print(result)

        if ("cursor" not in result and "user_list" not in result) or result["statusCode"] != 0:
            break

        for t in result.get("user_list", []):
            res.append(t)
            found += 1

        if not result.get("hasMore", False):
            return res

        params["cursor"] = result["cursor"]

    return res[:count]


def fetch_post_comments(post_id="7198199504405843205", count=10):
    base_url = f"https://www.tiktok.com/api/comment/list/"

    params = get_params()
    params["cursor"] = "0"
    params["from_page"] = "video"
    params["fromWeb"] = "1"
    params["app_language"] = "ja-JP"
    params["current_region"] = "JP"
    params["aweme_id"] = post_id
    params["is_non_personalized"] = "false"
    params["enter_from"] = "tiktok_web"

    res = []
    found = 0

    while found < count:
        result = fetch_data(encode_url(base_url, params), headers)
        print(result)

        if ("cursor" not in result and "comments" not in result) or result["total"] < 1:
            break

        for t in result.get("comments", []):
            res.append(t)
            found += 1

        if not result.get("hasMore", False):
            return res

        params["cursor"] = result["cursor"]

    return res[:count]


@threaded
def scrap_fashion_posts():
    instance["TaskLogs"] = "[=>] Scrapping Task started...<br><br>"
    print(f"[=>] Scrapping Task started...")

    instance["TaskLogs"] += '[=>] Starting Browser Instance<br>'
    print(f"[=>] Starting Browser Instance")
    session.playwright = sync_playwright().start()
    mobile_device = session.playwright.devices['iPhone 14 Pro Max']

    session.browser = session.playwright.chromium.launch(
        headless=True,
        args=["--user-agent={}".format(configs["UserAgent"])],
        ignore_default_args=["--mute-audio", "--hide-scrollbars"],
    )

    session.context = session.browser.new_context(
        **mobile_device,
        bypass_csp=True,
        locale=configs["Locale"],
        timezone_id=configs["TimeZone"],
    )

    session.page = session.context.new_page()
    session.page.goto(configs["DefaultURL"], wait_until="networkidle")
    session.info = session.page.evaluate("""() => {
          return {
            platform: window.navigator.platform,
            deviceScaleFactor: window.devicePixelRatio,
            user_agent: window.navigator.userAgent,
            screen_width: window.screen.width,
            screen_height: window.screen.height,
            history: window.history.length,
            browser_language: window.navigator.language,
            browser_platform: window.navigator.platform,
            browser_name: window.navigator.appCodeName,
            browser_version: window.navigator.appVersion,
          };
        }""")

    cookies = session.context.cookies()
    cookies = {cookie["name"]: cookie["value"] for cookie in cookies}
    instance["TaskLogs"] += f'[*] Cookies: {cookies}<br>[=>] Browser Ready!<br>[=>] Starting Scrapping!<br>'
    print(f"[=>] Browser Ready!")

    count = 0
    df_data = {
        "Post URL": [],
        "User": [],
        "Author Name": [],
        "Likes": [],
        "Views": [],
        "Shares": [],
        "Comments": [],
        "Comments Data": [],
        "Caption": [],
        "HashTags": [],
        "Music": [],
        "Date Posted": [],
        "Date Collected": [],
    }

    fashion_data = []

    # Fetch posts from different tags
    tags = [("fashion", 25), ("femaleoutfit", 25), ("fashionweek", 25), ("femalestreetwear", 25)]
    for tag in tags:
        post_data = fetch_tags_posts(tag[0], count=tag[1])
        if not post_data:
            print(f"[!] Failed to get to {tag[0]} Tag Posts")
            instance["TaskLogs"] += f"[!] Failed to get to {tag[0]} Tag Posts<br>"
        else:
            print(f'[=>] Tag: {tag[0]}, Count: {tag[1]}')
            instance["TaskLogs"] += f"[=>] Tag: {tag[0]}, Count: {tag[1]}<br>"
            fashion_data.extend(post_data)

    for rec in fashion_data:
        print(f'[=>] Post {count + 1}')
        instance["TaskLogs"] += f"[=>] Post {count + 1}<br>"
        # print(f'[*] ID: {rec["id"]}')

        desc = rec["desc"]
        hashpos = desc.find("#")
        hashtags = desc[hashpos:]
        desc = desc[:hashpos]

        # print(f'[*] Caption: {desc}')
        # print(f'[*] HashTags: {hashtags}')
        # print(f'[*] Like Count: {rec["stats"]["diggCount"]}')
        # print(f'[*] View Count: {rec["stats"]["playCount"]}')
        # print(f'[*] Share Count: {rec["stats"]["shareCount"]}')
        # print(f'[*] Comment Count: {rec["stats"]["commentCount"]}')
        # print(f'[*] Author: {rec["author"]["nickname"]}')
        # print(f'[*] Author User: {rec["author"]["uniqueId"]}')

        comments_data = []
        comments = get_comments_info(rec["author"]["uniqueId"], rec["id"])
        if not comments:
            print("[!] Failed to get to Comments for Post")
            instance["TaskLogs"] += f"[!] Failed to get to Comments for Post<br>"
        else:
            # print(f'[*] Total Comments: {comments["total"]}')
            for comts in comments["comments"]:
                comments_data.append(comts["text"])
                # print(f'[*] Comment: {comts["text"]}')

        # if 'music' in rec:
        #     print(f'[*] Post Music: {rec["music"]["title"]}')
        # print(f'[*] Post Date: {datetime.fromtimestamp(rec["createTime"])}')
        # print(f'[*] Collected Date: {datetime.now()}')
        # print(f'[*] Post URL: https://www.tiktok.com/@{rec["author"]["uniqueId"]}/{rec["id"]}')

        # Add to data cache
        df_data["Post URL"].append(f'https://www.tiktok.com/@{rec["author"]["uniqueId"]}/{rec["id"]}')
        df_data["User"].append(rec["author"]["uniqueId"])
        df_data["Author Name"].append(rec["author"]["nickname"])
        df_data["Likes"].append(rec["stats"]["diggCount"])
        df_data["Views"].append(rec["stats"]["playCount"])
        df_data["Shares"].append(rec["stats"]["shareCount"])
        df_data["Comments"].append(rec["stats"]["commentCount"])
        df_data["Comments Data"].append(comments_data)
        df_data["Caption"].append(desc)
        df_data["HashTags"].append(hashtags)
        df_data["Music"].append(rec["music"]["title"] if 'music' in rec else '')
        df_data["Date Posted"].append(datetime.fromtimestamp(rec["createTime"]))
        df_data["Date Collected"].append(datetime.now())

        count += 1

    instance["TaskLogs"] += f"[=>] Scrapping Completed, Please wait...<br>"

    # CSV export through dataframe
    df_fashion = pd.DataFrame(df_data)
    curr_timestamp = datetime.timestamp(datetime.now())
    scrap_file = f"sample_fashion_posts-{int(curr_timestamp)}.csv"
    createDir(joinPath(projectDir, "dumps"))
    file_path = joinPath(projectDir, "dumps", scrap_file)
    df_fashion.to_csv(file_path, index=False)

    instance["TaskLogs"] += f"[=>] Closing Browser Instance..<br>"
    session.browser.close()
    session.playwright.stop()

    instance["TaskLogs"] = ("[=>] Scrapping Completed: Download using this url: "
                            f"http://127.0.0.1:{server_port}/download/{scrap_file}<br>")
    instance["TaskRunning"] = False


# Server functions
@app.route("/", methods=['GET'])
def index():
    return "<p>Scraper Server Running...</p>"


@app.route("/scrap", methods=['GET'])
def scrapper():
    if not instance["TaskRunning"]:
        instance["TaskRunning"] = True
        scrap_fashion_posts()
        return "<p>Scrapping Task Started...</p>"
    else:
        return "<p>Task Already Running...</p>"


@app.route("/status", methods=['GET'])
def status():
    if not instance["TaskRunning"] and len(instance["TaskLogs"]) < 2:
        return "<p>Scrapping Not Started...</p>"
    else:
        return instance["TaskLogs"]


@app.route('/download/<path:filename>', methods=['GET'])
def downloadFile(filename):
    filename = str(filename).strip()
    # Simple file existence check
    file_path = joinPath(projectDir, "dumps", filename)
    if not isExist(file_path):
        return "<p>File not found!</p>"
    return send_file(file_path, as_attachment=True)


if __name__ == '__main__':
    print('[=>] TikTok Fashion Scraper Starting')

    print('[=>] Service Running on http://{}:{}'.format(server_host, server_port))
    app.run(host=server_host, port=int(server_port), debug=False)

    print("[=>] TikTok Fashion Scraper Stopped")
