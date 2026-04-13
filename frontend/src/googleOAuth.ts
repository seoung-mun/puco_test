export const googleClientId = ((import.meta.env.VITE_GOOGLE_CLIENT_ID as string | undefined) ?? '').trim();
export const googleLoginConfigured = googleClientId.length > 0;

export function getCurrentOrigin(
  locationLike: Pick<Location, 'origin' | 'protocol' | 'host'> = window.location,
): string {
  if (locationLike.origin) {
    return locationLike.origin;
  }
  return `${locationLike.protocol}//${locationLike.host}`;
}

export function buildGoogleLoginSetupMessage(options?: {
  origin?: string;
  googleClientConfigured?: boolean;
}): string {
  const origin = options?.origin ?? getCurrentOrigin();
  const googleClientConfigured = options?.googleClientConfigured ?? googleLoginConfigured;

  if (!googleClientConfigured) {
    return [
      'Google 로그인 설정이 비어 있습니다.',
      '프론트엔드에 `VITE_GOOGLE_CLIENT_ID`를 전달하고 이미지를 다시 빌드하세요.',
      `현재 접속 origin: ${origin}`,
    ].join(' ');
  }

  return [
    'Google 로그인 설정을 확인해주세요.',
    `현재 접속 origin: ${origin}`,
    'Google Cloud Console의 Authorized JavaScript origins에 이 origin을 추가해야 합니다.',
    'OAuth consent screen이 Testing 상태라면 팀원 계정을 Test users에 추가하거나 앱을 Publish 해야 합니다.',
    '백엔드 `ALLOWED_ORIGINS`에도 같은 origin이 포함되어야 합니다.',
  ].join(' ');
}
