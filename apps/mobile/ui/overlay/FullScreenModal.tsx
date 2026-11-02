import { Modal, StyleSheet, View, type ModalProps } from "react-native";

/**
 * A page that replaces the screen: image / PDF / text viewers, the HTML
 * preview, the math scanner, the full-screen graph. Popups are `Menu`,
 * `Dialog` and `Sheet` instead.
 *
 * Keep it mounted and drive `visible` from state. Returning null above an
 * open iOS modal skips RN's dismiss path and can leave the presenter stuck
 * (see the math-scanner lesson in .cursor/rules/lessons.mdc).
 */
type Props = Omit<ModalProps, "onRequestClose"> & {
  /** Android back, and VoiceOver's two-finger scrub. */
  onRequestClose: () => void;
};

export function FullScreenModal({ animationType = "slide", children, ...props }: Props) {
  return (
    <Modal animationType={animationType} {...props}>
      <View
        style={styles.page}
        collapsable={false}
        onAccessibilityEscape={props.onRequestClose}
        testID="full-screen-modal-page"
      >
        {children}
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({ page: { flex: 1 } });
