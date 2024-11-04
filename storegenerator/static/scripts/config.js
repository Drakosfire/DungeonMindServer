import dotenv from 'dotenv';

// Load environment variables from a .env file into process.env
dotenv.config();

let config = {
    DUNGEONMIND_BASE_URL: process.env.DUNGEONMIND_BASE_URL || '',
    DUNGEONMIND_API_URL: process.env.DUNGEONMIND_API_URL || '',
    ENVIRONMENT: process.env.ENVIRONMENT || '',
    CLOUDFLARE_ACCOUNT_ID: process.env.CLOUDFLARE_ACCOUNT_ID || '',
    CLOUDFLARE_IMAGES_API_TOKEN: process.env.CLOUDFLARE_IMAGES_API_TOKEN || ''
};

export function getConfig() {
    return config;
}
