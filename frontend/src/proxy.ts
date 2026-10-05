import { NextResponse, type NextRequest } from "next/server";

/**
 * Optimistic auth check: page requests without a session cookie go straight to /login.
 * The real session validation happens in the backend (every API call) and in the client guard.
 */
const PUBLIC_PATHS = ["/login"];

export function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  if (PUBLIC_PATHS.some((p) => pathname === p || pathname.startsWith(`${p}/`))) return NextResponse.next();
  if (request.cookies.has("nivara_session")) return NextResponse.next();
  const url = request.nextUrl.clone();
  url.pathname = "/login";
  url.search = pathname === "/" ? "" : `?next=${encodeURIComponent(pathname + search)}`;
  return NextResponse.redirect(url);
}

export const config = {
  // Everything except the API proxy, Next internals and static files.
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico|robots.txt|.*\\.(?:png|jpg|jpeg|svg|ico|webp|txt|xml)$).*)"],
};
