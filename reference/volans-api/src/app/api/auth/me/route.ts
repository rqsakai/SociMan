import { handleMe } from "@/handlers/auth";
import { getDefaultDeps } from "@/handlers/deps";

export const GET = (req: Request) => handleMe(req, getDefaultDeps());
