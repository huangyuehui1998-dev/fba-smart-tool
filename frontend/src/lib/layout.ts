export const SIDEBAR_WIDTH_EXPANDED = "340px";
export const SIDEBAR_WIDTH_COLLAPSED = "48px";
export const APP_SIDEBAR_WIDTH_VAR = "--app-sidebar-width";

export function sidebarWidthCss(open: boolean): string {
  return open ? SIDEBAR_WIDTH_EXPANDED : SIDEBAR_WIDTH_COLLAPSED;
}
