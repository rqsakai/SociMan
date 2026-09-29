import { handleLogout } from "@/handlers/auth";
import { getDefaultDeps } from "@/handlers/deps";

export const POST = (req: Request) => handleLogout(req, getDefaultDeps());
