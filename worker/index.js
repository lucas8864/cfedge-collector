export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    let path = url.pathname;

    if (path.endsWith("/")) {
      path = path.slice(0, -1);
    }

    const routes = {
      "/api": "stats.json",
      "/api/index": "index.json",
      "/api/stats": "stats.json",

      "/api/ipv4": "ip/ipv4.txt",
      "/api/ipv6": "ip/ipv6.txt",
      "/api/ip": "ip/all.txt",

      "/api/domain": "domain/all.txt",
      "/api/domain/top10": "domain/top10.txt",
      "/api/domain/top20": "domain/top20.txt",
      "/api/domain/top50": "domain/top50.txt",

      "/api/region/hk": "region/hk.txt",
      "/api/region/tw": "region/tw.txt",
      "/api/region/jp": "region/jp.txt",
      "/api/region/sg": "region/sg.txt",
      "/api/region/kr": "region/kr.txt",
      "/api/region/us": "region/us.txt",
      "/api/region/de": "region/de.txt",
      "/api/region/nl": "region/nl.txt",
      "/api/region/uk": "region/uk.txt",
      "/api/region/fr": "region/fr.txt",
      "/api/region/au": "region/au.txt",

      "/api/isp/cm": "isp/cm.txt",
      "/api/isp/cu": "isp/cu.txt",
      "/api/isp/ct": "isp/ct.txt",

      "/api/quality/latency100":
        "quality/latency100.txt",

      "/api/quality/latency200":
        "quality/latency200.txt",

      "/api/quality/speed50":
        "quality/speed50.txt",

      "/api/quality/speed100":
        "quality/speed100.txt",

      "/api/quality/score60":
        "quality/score60.txt",

      "/api/quality/score80":
        "quality/score80.txt"
    };

    if (path === "") {
      return json({
        name: "CFEdge Collector API",
        version: "1.0.0",
        endpoints: Object.keys(routes)
      });
    }

    const file = routes[path];

    if (!file) {
      return new Response(
        "Not Found",
        {
          status: 404,
          headers: {
            "content-type": "text/plain; charset=utf-8"
          }
        }
      );
    }

    const assetPath = "/data/" + file;

    const response =
      await env.ASSETS.fetch(
        new Request(
          new URL(
            assetPath,
            request.url
          )
        )
      );

    if (!response.ok) {
      return new Response(
        "Data Not Found",
        {
          status: 404
        }
      );
    }

    const headers =
      new Headers(
        response.headers
      );

    headers.set(
      "Access-Control-Allow-Origin",
      "*"
    );

    headers.set(
      "Cache-Control",
      "public, max-age=300"
    );

    return new Response(
      response.body,
      {
        status: response.status,
        headers
      }
    );
  }
};


function json(data) {
  return new Response(
    JSON.stringify(
      data,
      null,
      2
    ),
    {
      headers: {
        "content-type":
          "application/json; charset=utf-8",

        "Access-Control-Allow-Origin":
          "*"
      }
    }
  );
}

