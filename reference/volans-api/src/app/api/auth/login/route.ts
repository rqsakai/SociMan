import { handleLogin } from "@/handlers/auth";
import { getDefaultDeps } from "@/handlers/deps";

export const POST = (req: Request) => handleLogin(req, getDefaultDeps());
