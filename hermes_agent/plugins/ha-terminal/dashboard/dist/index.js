(function () {
  "use strict";

  const SDK = window.__HERMES_PLUGIN_SDK__;
  if (!SDK || !window.__HERMES_PLUGINS__) return;

  const { React } = SDK;
  const { useCallback, useEffect, useRef, useState } = SDK.hooks;
  const { Button } = SDK.components;
  const currentScript = document.currentScript;
  const assetBase = currentScript && currentScript.src
    ? currentScript.src.replace(/\/dist\/index\.js(?:\?.*)?$/, "")
    : "";

  function loadScript(file, globalName) {
    if (window[globalName]) return Promise.resolve();
    return new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = assetBase + "/dist/" + file;
      script.async = true;
      script.onload = resolve;
      script.onerror = () => reject(new Error("Could not load " + file));
      document.head.appendChild(script);
    });
  }

  function TerminalPage() {
    const hostRef = useRef(null);
    const terminalRef = useRef(null);
    const socketRef = useRef(null);
    const [generation, setGeneration] = useState(0);
    const [state, setState] = useState("Loading terminal…");
    const [ready, setReady] = useState(false);

    const writeCommand = useCallback((command) => {
      const socket = socketRef.current;
      if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: "input", data: command + "\r" }));
      }
      terminalRef.current?.focus();
    }, []);

    useEffect(() => {
      let cancelled = false;
      Promise.all([loadScript("xterm.js", "Terminal"), loadScript("xterm-fit.js", "FitAddon")])
        .then(() => { if (!cancelled) setReady(true); })
        .catch((error) => { if (!cancelled) setState(error.message); });
      return () => { cancelled = true; };
    }, []);

    useEffect(() => {
      if (!ready || !hostRef.current) return undefined;
      let cancelled = false;
      const terminal = new window.Terminal({
        cursorBlink: true,
        convertEol: true,
        fontFamily: "'JetBrains Mono', Menlo, Consolas, monospace",
        fontSize: 14,
        scrollback: 5000,
        theme: { background: "#000000", foreground: "#f0e6d2" },
      });
      const fit = new window.FitAddon.FitAddon();
      terminal.loadAddon(fit);
      terminal.open(hostRef.current);
      terminalRef.current = terminal;

      const sendResize = () => {
        try { fit.fit(); } catch (_) { return; }
        const socket = socketRef.current;
        if (socket && socket.readyState === WebSocket.OPEN) {
          socket.send(JSON.stringify({ type: "resize", cols: terminal.cols, rows: terminal.rows }));
        }
      };
      const resizeObserver = new ResizeObserver(sendResize);
      resizeObserver.observe(hostRef.current);
      const input = terminal.onData((data) => {
        const socket = socketRef.current;
        if (socket && socket.readyState === WebSocket.OPEN) {
          socket.send(JSON.stringify({ type: "input", data }));
        }
      });

      void SDK.buildWsUrl("/api/plugins/ha-terminal/terminal").then((url) => {
        if (cancelled) return;
        const socket = new WebSocket(url);
        socket.binaryType = "arraybuffer";
        socketRef.current = socket;
        socket.onopen = () => { setState("Connected"); sendResize(); terminal.focus(); };
        socket.onmessage = (event) => {
          if (typeof event.data === "string") {
            try {
              const frame = JSON.parse(event.data);
              if (frame.type === "error") setState(frame.message || "Terminal error");
              else terminal.write(event.data);
            } catch (_) { terminal.write(event.data); }
          } else {
            terminal.write(new TextDecoder().decode(event.data));
          }
        };
        socket.onerror = () => setState("Terminal WebSocket error. Reconnect to try again.");
        socket.onclose = () => { if (!cancelled) setState("Terminal disconnected. Reconnect to start a new shell."); };
      }).catch((error) => setState("Terminal connection failed: " + error.message));

      return () => {
        cancelled = true;
        input.dispose();
        resizeObserver.disconnect();
        socketRef.current?.close();
        socketRef.current = null;
        terminal.dispose();
        terminalRef.current = null;
      };
    }, [ready, generation]);

    return React.createElement("div", { className: "ha-terminal-page" },
      React.createElement("div", { className: "ha-terminal-toolbar" },
        React.createElement("span", { className: "ha-terminal-status" }, state),
        React.createElement(Button, { size: "sm", outlined: true, onClick: () => writeCommand("hermes setup") }, "Hermes Setup"),
        React.createElement(Button, { size: "sm", outlined: true, onClick: () => writeCommand("hermes model") }, "Configure Model"),
        React.createElement(Button, { size: "sm", outlined: true, onClick: () => writeCommand("ha core info") }, "HA Info"),
        React.createElement(Button, { size: "sm", onClick: () => setGeneration((value) => value + 1) }, "New Terminal")
      ),
      React.createElement("div", { ref: hostRef, className: "ha-terminal-host", role: "application", "aria-label": "Hermes container terminal" })
    );
  }

  window.__HERMES_PLUGINS__.register("ha-terminal", TerminalPage);
})();
