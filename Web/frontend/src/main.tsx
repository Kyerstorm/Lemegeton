import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App";

const root = document.getElementById("app");
if (!root) throw new Error("The Lemegeton dashboard mount point is missing.");
createRoot(root).render(<React.StrictMode><App /></React.StrictMode>);
