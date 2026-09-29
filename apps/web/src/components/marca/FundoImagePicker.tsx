import { fundosKey } from "../../lib/marca";
import { api } from "../../lib/api";
import { ProfileImagePicker, type ProfileImagePickerProps } from "./ProfileImagePicker";

// Imagem de fundo do gancho e do card final (FR-005b, T033): PNG, JPG ou WebP, até 5 MB, mínimo
// 540×540. As duas seções escolhem da mesma lista do perfil.
export function FundoImagePicker({ perfilId, ...props }: ProfileImagePickerProps & { perfilId: string }) {
  return (
    <ProfileImagePicker
      {...props}
      queryKey={fundosKey(perfilId)}
      list={() => api.fundos.list(perfilId)}
      upload={(file) => api.fundos.upload(perfilId, file)}
      label="Imagem de fundo"
      uploadLabel="Enviar imagem de fundo"
      hint="PNG, JPG ou WebP, até 5 MB, mínimo 540×540 px. A imagem é recortada para preencher a área."
      accepted={["image/png", "image/jpeg", "image/webp"]}
      minSize={540}
    />
  );
}
