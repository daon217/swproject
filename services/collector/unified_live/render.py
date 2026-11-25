"""Optional standard Chromium, no stealth. Every resource is same-origin and budgeted."""
from urllib.parse import urlsplit
import time
from datetime import timedelta
import os
from .policy import url
from .transport import Wait

class PlaywrightRenderer:
    def render(self,target,transport):
        try:from playwright.sync_api import sync_playwright
        except ImportError:raise Wait('optional_playwright_and_Chromium_not_installed',hold=True) from None
        errors=[]
        with sync_playwright() as p:
            channel=os.environ.get('COLLECTOR_BROWSER_CHANNEL') or None
            if channel not in (None,'chrome','msedge'):raise Wait('reviewed_browser_channel_required',hold=True)
            browser=p.chromium.launch(headless=True,channel=channel,args=['--disable-background-networking','--disable-dns-prefetch',
                '--disable-component-update','--disable-sync','--no-first-run','--disable-default-apps','--disable-features=WebRtcHideLocalIpsWithMdns'])
            context=browser.new_context(service_workers='block',accept_downloads=False,user_agent='KkulpickCollector/1.0')
            if not hasattr(context,'route_web_socket'):
                context.close();browser.close();raise Wait('reviewed_Playwright_websocket_blocking_required',hold=True)
            context.route_web_socket('**/*',lambda route:route.close())
            context.add_init_script('globalThis.RTCPeerConnection=undefined; globalThis.webkitRTCPeerConnection=undefined; globalThis.Worker=undefined; globalThis.SharedWorker=undefined;')
            deadline=time.monotonic()+25
            def route(request_route):
                request=request_route.request
                try:
                    if request.method!='GET' or request.resource_type in ('image','media','font','websocket','eventsource'):request_route.abort();return
                    safe=url(request.url,transport.host)
                    for _ in range(4):
                        try:code,html=transport.fetch(safe);break
                        except Wait as exc:
                            delay=(exc.until-transport.clock()).total_seconds() if exc.until else 999
                            if exc.hold or str(exc) not in ('rate_wait','robots_crawl_delay','robots_request_rate') or not 0<delay<=20 or time.monotonic()+delay>=deadline:raise
                            time.sleep(delay)
                    else:raise Wait('browser_resource_rate_review_required',hold=True)
                    mime='text/html' if request.resource_type=='document' else 'text/javascript' if request.resource_type=='script' else 'text/css' if request.resource_type=='stylesheet' else 'application/json'
                    request_route.fulfill(status=code,body=html,content_type=mime)
                except (Wait,ValueError) as exc:errors.append(exc);request_route.abort()
            context.route('**/*',route)
            try:
                page=context.new_page()
                try:
                    page.goto(target,wait_until='networkidle',timeout=20000)
                    html=page.content()
                except Exception:
                    if errors:raise errors[0]
                    raise Wait('browser_render_error',transport.clock()+timedelta(seconds=60)) from None
                if errors:raise errors[0]
                return html
            finally:context.close();browser.close()
