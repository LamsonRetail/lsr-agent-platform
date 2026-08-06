/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: "standalone", // build gọn để chạy trong Docker (node server.js)
};
export default nextConfig;
