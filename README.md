# Tiktok-Scrapper-Challenge

Solution of a small coding challenge given to me to create a poc scrapper for the TikTok

### Detail Notes

- Mobile mode runs like application and even after some restrictions, captcha are main problems with desktop browser more, So I opted for mobile UserAgent.
- started by looking into html structure of the origin url, found rehydration state data that stores some important information for the js framework
- utilized BeautifulSoup to extract data from the html and json decode to load them. first error encountered was related to data which was html escaped, so before giving to decoder I first needed to unescape the text first.
- first major API for data I found was related to Recommendation for the main page. https://www.tiktok.com/api/recommend/item_list/
- each user page have webapp.user-detail in state data. which contains users related information, second most important field apart from userid is secUID which is encrypted form of token for userID and secUID is used by other apis to identify user. 
```
"webapp.user-detail": {
    "userInfo": {
        "user": {
            "id": "160822079959736320",
            "uniqueId": "redbull",
            "nickname": "Red Bull",
            "signature": "welcome to the world of Red Bull 👐\n#givesyouwiiings",
            "verified": true,
            "secUid": "MS4wLjABAAAAhIB9TB7M0IlBNyge2BpxJL0dMV30Qd4kyRwZsYIBl_9cRDf8tMN2LQX_VnK-JfTh",
            "region": "AT",
            ...
        },
        "stats": {
            "followerCount": 10300000,
            "followingCount": 427,
            "heart": 195300000,
            "heartCount": 195300000,
            "videoCount": 3339,
            "diggCount": 0,
            "friendCount": 265
        },
        ...
    },
    "shareMeta": {
        "title": "Red Bull on TikTok",
        "desc": "@redbull 10.3m Followers, 427 Following, 195.3m Likes - Watch awesome short videos created by Red Bull"
    },
}
```
- second major API was for user post. https://www.tiktok.com/api/post/item_list/ which required secUID to fetch user's post.
- Seems like apis are secured using a nonce parameter[X-Bogus] which acts like signature for the session token[ms_Token] and url, and would pass with the param data to api.
  This functionality is archived on the client side using a obfuscated js file called webmssdk.js: https://lf16-tiktok-web.tiktokcdn-us.com/obj/tiktok-web-tx/webmssdk/2.0.0.210/webmssdk.js
  Which perform some crypto operations to generate the nonce for the apis.
- ~~There is also a _signature field which is right now unknown to me.~~ Found a repo for nonce and signature generation,
  Need to adapt the functions to do that: https://github.com/carcabot/tiktok-signature
- After looking at the call stack, I noticed that the fetch api is hooked internally by their js code to automatically insert [ms_Token], [X-Bogus] and [_signature] data.
- Instead of complicating stuffs I simply opted for browser automation, so I don't need to perform any complex operations myself. 
  I am using Playwright which is amazing alternative of selenium. https://playwright.dev/
- 3 big problems are clearly the size of the browser runtime, high memory usage and slow startup time even in headless mode.
- Search api https://www.tiktok.com/api/search/ seems secured by captcha and not accessible even in headless browser, need to explore more.
- Comments list for Post with api https://www.tiktok.com/api/comment/list/ seems not accessible, need to explore more. Instead, using posts html for initial comments of the preload page.
- To generate csv in proper format, I opted for Pandas library which provides easy apis for the same.
- To convert this tool into rest-full service, I opted for Flask library which help set up the small server.
- Utilized Docker to containerise the service.

#### Build

```sh
docker build . -t tiktok-challenge
```

#### Run

```sh
docker run -p 8000:8000 tiktok-challenge
```

- Running server with single process - single task for testing purpose.
- After running on the docker, service will be forward to localhost:8000

```code
Start Scrapping Task: http://localhost:8000/scrap
Check Scrapping Status: http://localhost:8000/status
Download Dumped File: http://localhost:8000/download/[path]
```