export const THEME_STORAGE_KEY = "researchassistant-theme";

/** Runs before first paint so an explicit choice does not flash the other theme. */
export const themeBootScript = `try{var t=localStorage.getItem(${JSON.stringify(THEME_STORAGE_KEY)});if(t==="light"||t==="dark")document.documentElement.setAttribute("data-theme",t)}catch(e){}`;
