import { marcaDaguaKey } from "../../lib/marca";
import { api } from "../../lib/api";
import { ProfileImagePicker, type ProfileImagePickerProps } from "./ProfileImagePicker";

// Imagem própria da marca d'água (T020): PNG ou WebP com transparência, até 5 MB, mínimo 64×64
// (o servidor confere o alfa).
export function WatermarkImagePicker({ perfilId, ...props }: ProfileImagePickerProps & { perfilId: string }) {
  return (
    <ProfileImagePicker
      {...props}
      queryKey={marcaDaguaKey(perfilId)}
      list={() => api.marcaDagua.list(perfilId)}
      upload={(file) => api.marcaDagua.upload(perfilId, file)}
      label="Imagem da marca d'água"
      uploadLabel="Enviar imagem"
      hint="PNG ou WebP com fundo transparente, até 5 MB, mínimo 64×64 px."
      accepted={["image/png", "image/webp"]}
      minSize={64}
      transparent
    />
  );
}
