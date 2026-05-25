import { withAuth } from "next-auth/middleware";
import { NextResponse } from "next/server";

export default withAuth(
  function middleware(req) {
    const token = req.nextauth.token;
    const { pathname } = req.nextUrl;

    // Block platform admin routes for non-admin users
    if (pathname.startsWith("/admin") && token?.role !== "PlatformAdmin") {
      return NextResponse.redirect(new URL("/dashboard", req.url));
    }

    return NextResponse.next();
  },
  {
    callbacks: {
      authorized: ({ token }) => !!token,
    },
  }
);

export const config = {
  matcher: [
    "/dashboard/:path*",
    "/campaigns/:path*",
    "/outreach/:path*",
    "/analytics/:path*",
    "/admin/:path*",
  ],
};
