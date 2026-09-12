import { analyticsGet, analyticsErrorResponse } from "@/lib/analytics-client";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: Request, context: { params: Promise<{ path: string[] }> }) {
  try {
    const { path } = await context.params;
    return Response.json(await analyticsGet(path.join("/"), new URL(request.url).searchParams), {
      headers: { "Cache-Control": "no-store" },
    });
  } catch (error) {
    return analyticsErrorResponse(error);
  }
}
