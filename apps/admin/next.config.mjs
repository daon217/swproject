/** @type {import('next').NextConfig} */
const nextConfig = {
  // Docker 이미지에는 실행에 필요한 파일만 담는다(.next/standalone). 개발(npm run dev)에는 영향 없음.
  output: 'standalone',
};

export default nextConfig;
