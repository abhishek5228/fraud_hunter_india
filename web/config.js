/* Where the API lives. Leave empty when the page is served by the Python backend itself.
   For a split deploy (static frontend on Netlify/Vercel/Pages, API elsewhere) set the backend URL,
   e.g. window.FH_API = "https://fraud-hunter.onrender.com"; */
window.FH_API = window.FH_API || "";
/* Only for a PRIVATE deployment where the server sets FH_API_KEY. Anything in this file is visible to every visitor, so never
   put a key here on a public site. */
window.FH_KEY = window.FH_KEY || "";
