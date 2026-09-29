import { handleResetPassword } from "@/handlers/auth";
import { getDefaultDeps } from "@/handlers/deps";

export const POST = (req: Request) => handleResetPassword(req, getDefaultDeps());
