/**
 * app/(app)/(tabs)/home.tsx — Dashboard principal
 */
import { ScrollView, View, Text, StyleSheet, TouchableOpacity, ActivityIndicator } from "react-native";
import { useQuery } from "@tanstack/react-query";
import { router } from "expo-router";
import { useAuth } from "../../../store/authStore";
import { apiClient } from "../../../lib/apiClient";
import { API_ROUTES } from "@shared/constants";
import type { Entitlements, Module } from "@shared/types";

export default function HomeScreen() {
  const { user, logout } = useAuth();

  const { data: entitlements, isLoading: loadingEnt } = useQuery<Entitlements>({
    queryKey: ["entitlements"],
    queryFn: () => apiClient.get(API_ROUTES.ENTITLEMENTS_ME),
  });

  const { data: modules, isLoading: loadingMod } = useQuery<Module[]>({
    queryKey: ["mobile-modules"],
    queryFn: () => apiClient.get("/api/v1/modules/catalog/mobile"),
  });

  const PLAN_COLOR: Record<string, string> = {
    free: "#555", pro: "#7C3AED", business: "#F59E0B",
  };

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      {/* Header */}
      <View style={styles.header}>
        <View>
          <Text style={styles.greeting}>Bonjour, {user?.full_name?.split(" ")[0]} 👋</Text>
          <Text style={styles.subtitle}>Bienvenue sur Nanovia OS</Text>
        </View>
        <View style={[styles.planBadge, { backgroundColor: PLAN_COLOR[user?.plan ?? "free"] + "33" }]}>
          <Text style={[styles.planText, { color: PLAN_COLOR[user?.plan ?? "free"] }]}>
            {user?.plan?.toUpperCase()}
          </Text>
        </View>
      </View>

      {/* Entitlements card */}
      {loadingEnt ? (
        <ActivityIndicator color="#7C3AED" style={{ marginVertical: 20 }} />
      ) : entitlements ? (
        <View style={styles.card}>
          <Text style={styles.cardTitle}>Ton plan</Text>
          <Text style={styles.cardValue}>{entitlements.plan.toUpperCase()}</Text>
          <Text style={styles.cardSub}>
            {entitlements.limits.ai_messages_per_month === -1
              ? "Messages illimités"
              : `${entitlements.limits.ai_messages_per_month} messages / mois`}
          </Text>
          {entitlements.plan === "free" && (
            <TouchableOpacity
              style={styles.upgradeButton}
              onPress={() => router.push("/(app)/billing")}
            >
              <Text style={styles.upgradeText}>Passer à Pro →</Text>
            </TouchableOpacity>
          )}
        </View>
      ) : null}

      {/* Mobile modules */}
      <Text style={styles.sectionTitle}>Modules disponibles</Text>
      {loadingMod ? (
        <ActivityIndicator color="#7C3AED" />
      ) : (
        modules?.map((m) => (
          <TouchableOpacity
            key={m.key}
            style={[styles.moduleCard, !m.is_available && styles.moduleDisabled]}
            onPress={() => m.is_available && router.push(`/(app)/modules/${m.key}`)}
          >
            <Text style={styles.moduleName}>{m.name}</Text>
            <Text style={styles.moduleDesc}>{m.description}</Text>
            {!m.is_available && (
              <Text style={styles.moduleUpgrade}>Upgrade requis</Text>
            )}
          </TouchableOpacity>
        ))
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#0A0A0F" },
  content: { padding: 20, paddingTop: 60 },
  header: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: 24 },
  greeting: { fontSize: 22, fontWeight: "700", color: "#FFF" },
  subtitle: { fontSize: 13, color: "#666", marginTop: 2 },
  planBadge: { paddingHorizontal: 12, paddingVertical: 4, borderRadius: 20 },
  planText: { fontWeight: "700", fontSize: 12 },
  card: { backgroundColor: "#1A1A2E", borderRadius: 16, padding: 20, marginBottom: 24 },
  cardTitle: { color: "#888", fontSize: 12, fontWeight: "600", marginBottom: 4 },
  cardValue: { color: "#FFF", fontSize: 28, fontWeight: "800" },
  cardSub: { color: "#666", fontSize: 13, marginTop: 4 },
  upgradeButton: { backgroundColor: "#7C3AED", borderRadius: 8, padding: 10, alignItems: "center", marginTop: 12 },
  upgradeText: { color: "#FFF", fontWeight: "700" },
  sectionTitle: { color: "#FFF", fontSize: 18, fontWeight: "700", marginBottom: 12 },
  moduleCard: { backgroundColor: "#1A1A2E", borderRadius: 12, padding: 16, marginBottom: 10, borderWidth: 1, borderColor: "#2A2A4A" },
  moduleDisabled: { opacity: 0.5 },
  moduleName: { color: "#FFF", fontWeight: "700", fontSize: 15 },
  moduleDesc: { color: "#888", fontSize: 12, marginTop: 4 },
  moduleUpgrade: { color: "#F59E0B", fontSize: 11, marginTop: 6, fontWeight: "600" },
});
