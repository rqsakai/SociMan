import { handleForgotPassword } from "@/handlers/auth";
import { getDefaultDeps } from "@/handlers/deps";

export const POST = (req: Request) => handleForgotPassword(req, getDefaultDeps());
