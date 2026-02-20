import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";

import "../../src/static/css/base.css";
import "../../src/static/css/layout.css";
import "../../src/static/css/components.css";
import "../../src/static/css/views.css";

const rootElement = document.getElementById("root");
if (!rootElement) {
  throw new Error("Unable to find root element");
}

ReactDOM.createRoot(rootElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
