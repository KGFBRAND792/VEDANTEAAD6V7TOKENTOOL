
 * Group Name Locker Bot (Fast + Instant Reset)
 * Developer: Axshu 🩷
 * Description: This bot locks the group name and resets it instantly if changed.
 */

const login = require("ws3-fca");
const fs = require("fs");
const express = require("express");

// ✅ Load AppState
let appState;
try {
  appState = JSON.parse(fs.readFileSync("appstate.json", "utf-8"));
} catch (err) {
  console.error("❌ Error reading appstate.json:", err);
  process.exit(1);
}

// ✅ Group Info (change these)
const GROUP_THREAD_ID = "856688617244149";        // Group ka ID
const LOCKED_GROUP_NAME = "कार्तिक राजपूत + विक्की + एजे+ ऑल हेल्पर चोद कर मर जाएंगे पठान हेयर 👈";     // Locked name

// ✅ Express Server to keep bot alive (for Render or UptimeRobot)
const app = express();
const PORT = process.env.PORT || 3000;
app.get("/", (req, res) =>
  res.send("🤖 Group Name Locker Bot is alive! 👨‍💻 Developer: Axshu 🩷")
);
app.listen(PORT, () =>
  console.log(`🌐 Web server running on port ${PORT}`)
);

/**
 * Safe function to set title with logging and simple retry.
 */
function safeSetTitle(api, title, threadID, cb) {
  api.setTitle(title, threadID, (err) => {
    if (err) {
      console.error(
        `❌ safeSetTitle failed to set "${title}" on ${threadID}:`,
        err
      );
      if (typeof cb === "function") cb(err);
    } else {
      console.log(`🔒 Group title set to "${title}" on ${threadID}`);
      if (typeof cb === "function") cb(null);
    }
  });
}

/**
 * Polling fallback: checks group name every `pollIntervalMs`.
 */
function startPollingFallback(api, pollIntervalMs = 30 * 1000) {
  let stopped = false;

  function loop() {
    if (stopped) return;
    api.getThreadInfo(GROUP_THREAD_ID, (err, info) => {
      if (err) {
        console.error("❌ Polling: error fetching group info:", err);
        return setTimeout(loop, 60 * 1000);
      }

      const currentName = info?.name || info?.threadName || "Unknown";
      if (currentName !== LOCKED_GROUP_NAME) {
        console.warn(
          `⚠️ Polling detected name change ("${currentName}") → resetting immediately...`
        );
        safeSetTitle(api, LOCKED_GROUP_NAME, GROUP_THREAD_ID, () => {
          setTimeout(loop, 5 * 1000);
        });
      } else {
        setTimeout(loop, pollIntervalMs);
      }
    });
  }
  loop();

  return () => {
    stopped = true;
  };
}

/**
 * Event-driven instant reset
 */
function startEventListener(api) {
  try {
    api.listenMqtt((err, event) => {
      if (err) return console.error("❌ listenMqtt error:", err);

      if (event && event.type === "event" && event.logMessageType) {
        const t = event.logMessageType.toString();
        const looksLikeTitleChange =
          t === "log:thread-name" ||
          t === "log:thread-title" ||
          t === "log:thread-name-change" ||
          (t.includes("thread") && t.includes("name")) ||
          (t.includes("thread") && t.includes("title"));

        if (looksLikeTitleChange) {
          const threadId =
            event.threadID ||
            event.logMessageData?.threadID ||
            event.logMessageData?.threadId;

          if (threadId === GROUP_THREAD_ID) {
            console.warn("⚠️ Event-driven: group title change detected.");
            setTimeout(() => {
              safeSetTitle(api, LOCKED_GROUP_NAME, GROUP_THREAD_ID, (err) => {
                if (err) {
                  console.error(
                    "❌ Event-driven: failed to reset title:",
                    err
                  );
                } else {
                  console.log("🔁 Event-driven: reset executed.");
                }
              });
            }, 200);
          }
        }
      }
    });
  } catch (e) {
    console.error("❌ startEventListener crashed:", e);
  }
}

// 🟢 Facebook Login
login({ appState }, (err, api) => {
  if (err) {
    console.error("❌ Login Failed:", err);
    return;
  }

  console.log("✅ Logged in successfully.");
  console.log("👨‍💻 Developer: Axshu 🩷");
  console.log("🚀 Group name locker (fast + instant) activated.");

  startEventListener(api); // Event-driven instant reset
  startPollingFallback(api, 30 * 1000); // Polling fallback
});
