// Object Storage S3-compatível (MinIO no docker-compose; S3/compatível em
// produção fora da Azion). forcePathStyle é necessário para MinIO.
import {
  DeleteObjectCommand,
  GetObjectCommand,
  PutObjectCommand,
  S3Client,
} from "@aws-sdk/client-s3";
import type { ObjectStorage } from "../storage";

export interface S3Config {
  endpoint?: string;
  region: string;
  accessKey: string;
  secretKey: string;
  bucket: string;
}

export function createS3Storage(config: S3Config): ObjectStorage {
  const client = new S3Client({
    endpoint: config.endpoint,
    region: config.region,
    forcePathStyle: Boolean(config.endpoint),
    credentials: { accessKeyId: config.accessKey, secretAccessKey: config.secretKey },
  });

  return {
    async put(key, body, contentType) {
      await client.send(
        new PutObjectCommand({
          Bucket: config.bucket,
          Key: key,
          Body: typeof body === "string" ? new TextEncoder().encode(body) : body,
          ContentType: contentType,
        }),
      );
    },

    async get(key) {
      try {
        const res = await client.send(new GetObjectCommand({ Bucket: config.bucket, Key: key }));
        return res.Body ? new Uint8Array(await res.Body.transformToByteArray()) : null;
      } catch (err) {
        if ((err as { name?: string }).name === "NoSuchKey") return null;
        throw err;
      }
    },

    async delete(key) {
      await client.send(new DeleteObjectCommand({ Bucket: config.bucket, Key: key }));
    },
  };
}
